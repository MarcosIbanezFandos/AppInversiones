import math
from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass
class Portfolio:
    holdings: Dict[str, float]        # valor actual en € por activo
    targets: Dict[str, float]         # porcentaje objetivo (0–1) por activo
    asset_types: Dict[str, str] | None = None  # tipo de activo (acción, ETF, bono, cripto, etc.)

    def total_value(self) -> float:
        return sum(self.holdings.values())

    def current_weights(self) -> Dict[str, float]:
        total = self.total_value()
        if total == 0:
            return {k: 0.0 for k in self.holdings}
        return {k: v / total for k, v in self.holdings.items()}


def compute_contribution_plan(
    portfolio: Portfolio,
    monthly_contribution: float,
    rebalance_threshold: float = 0.0,
) -> Dict[str, float]:
    """Devuelve cuánto deberías aportar este mes a cada activo
    para acercarte a los porcentajes objetivo, usando SOLO aportación
    (no venta), con la opción de usar un umbral de rebalanceo.
    """
    holdings = portfolio.holdings
    targets = portfolio.targets

    if set(holdings.keys()) != set(targets.keys()):
        raise ValueError("Las claves de holdings y targets deben coincidir.")

    total_before = portfolio.total_value()
    total_after = total_before + monthly_contribution

    current_w = portfolio.current_weights()

    needed_raw: Dict[str, float] = {}
    for asset, target_w in targets.items():
        target_value = target_w * total_after
        current_value = holdings[asset]

        if rebalance_threshold > 0:
            curr_weight = current_w.get(asset, 0.0)
            diff = abs(curr_weight - target_w)
            if diff < rebalance_threshold:
                needed = max(0.0, target_value - current_value)
            else:
                needed = max(0.0, target_value - current_value)
        else:
            needed = max(0.0, target_value - current_value)

        needed_raw[asset] = needed

    total_needed = sum(needed_raw.values())

    if total_needed == 0:
        return {
            asset: monthly_contribution * targets[asset]
            for asset in holdings
        }

    contributions: Dict[str, float] = {}
    for asset, needed in needed_raw.items():
        if total_needed == 0:
            share = 0.0
        else:
            share = needed / total_needed
        contributions[asset] = share * monthly_contribution

    contributions = {
        asset: int(round(amount)) for asset, amount in contributions.items()
    }

    diff = int(round(monthly_contribution - sum(contributions.values())))
    if diff != 0:
        biggest = max(contributions, key=lambda k: contributions[k])
        contributions[biggest] = contributions[biggest] + diff

    return contributions


def simulate_dca_ramp(
    initial_monthly: float,
    final_monthly: float,
    years: int,
    annual_return: float,
    initial_value: float = 0.0,
) -> Tuple[float, List[float]]:
    """Simula un plan donde:
      - Empiezas aportando `initial_monthly` €/mes
      - Terminas aportando `final_monthly` €/mes tras N años
      - Aportación sube linealmente mes a mes
      - Rentabilidad anual constante
      - Devuelve: valor final y serie mensual de valores
    """
    months = years * 12
    if months <= 0:
        raise ValueError("years debe ser > 0")

    monthly_values: List[float] = []
    value = initial_value
    r_m = (1 + annual_return) ** (1 / 12) - 1

    for m in range(months):
        if months == 1:
            contrib = final_monthly
        else:
            contrib = initial_monthly + (final_monthly - initial_monthly) * (m / (months - 1))

        value += contrib
        value *= (1 + r_m)

        monthly_values.append(value)

    return value, monthly_values


# === Funciones utilitarias para uso en Streamlit/app ===
def required_constant_monthly_for_goal(
    current_total: float,
    objetivo_final: float,
    years: int,
    annual_return: float,
    extra_savings: float = 0.0,
    tax_rate: float = 0.0,
) -> int:
    """Calcula la aportación mensual constante necesaria para alcanzar un objetivo_final
    en `years` años con una rentabilidad anual `annual_return`.

    Tiene en cuenta:
      - el valor actual de la cartera (`current_total`),
      - unos ahorros extra opcionales (`extra_savings`),
      - y opcionalmente un tipo impositivo `tax_rate` (0–1) sobre las plusvalías al final,
        asumiendo que se vende todo al final del periodo.

    Devuelve un entero (euros/mes) adecuado para planes tipo Trade Republic.
    """
    if years <= 0:
        raise ValueError("years debe ser > 0")
    if annual_return < 0:
        raise ValueError("annual_return no puede ser negativo")
    if not (0.0 <= tax_rate <= 1.0):
        raise ValueError("tax_rate debe estar entre 0 y 1")

    months = years * 12

    def net_final_with_monthly(C: float) -> float:
        """Calcula el patrimonio neto al final (después de impuestos sobre plusvalías)
        utilizando una aportación mensual constante C.
        """
        C_int = int(round(C))
        if C_int < 0:
            C_int = 0
        final_value, _ = simulate_constant_plan(
            current_total=current_total,
            monthly_contribution=C_int,
            years=years,
            annual_return=annual_return,
            extra_savings=extra_savings,
        )
        principal_total = current_total + extra_savings + C_int * months
        gain = max(0.0, final_value - principal_total)
        tax = tax_rate * gain
        net_final = final_value - tax
        return net_final

    # Si con 0 €/mes ya se alcanza el objetivo neto, no hace falta aportar
    if net_final_with_monthly(0.0) >= objetivo_final:
        return 0

    # Búsqueda binaria sobre la aportación mensual necesaria
    low = 0.0
    high = max(objetivo_final / max(months, 1) * 2, 5000.0)
    for _ in range(40):
        mid = (low + high) / 2
        net_val = net_final_with_monthly(mid)
        if net_val < objetivo_final:
            low = mid
        else:
            high = mid

    return int(round(high))


def simulate_constant_plan(
    current_total: float,
    monthly_contribution: int,
    years: int,
    annual_return: float,
    extra_savings: float = 0.0,
) -> Tuple[float, List[float]]:
    """Simula un plan de aportaciones mensuales constantes, partiendo de un valor
    inicial (cartera + ahorros extra) y devolviendo el valor final y la serie
    mensual de valores.
    """
    if years <= 0:
        raise ValueError("years debe ser > 0")
    months = years * 12
    r_m = (1 + annual_return) ** (1 / 12) - 1

    value = current_total + extra_savings
    monthly_values: List[float] = []

    for _ in range(months):
        value += monthly_contribution
        value *= (1 + r_m)
        monthly_values.append(value)

    return value, monthly_values


def required_growing_monthlies_for_goal(
    current_total: float,
    objetivo_final: float,
    years: int,
    annual_return: float,
    initial_monthly: int,
    extra_savings: float = 0.0,
    tax_rate: float = 0.0,
) -> Tuple[int, List[Dict[str, int]]]:
    """Calcula una aportación mensual creciente (lineal) para alcanzar un objetivo.

    Mantiene `initial_monthly` como aportación inicial y busca por búsqueda binaria
    la aportación mensual final necesaria para aproximarse al objetivo.

    Tiene en cuenta opcionalmente un tipo impositivo `tax_rate` (0–1) sobre las
    plusvalías al final, asumiendo que se vende todo al final del periodo.

    Devuelve:
      - final_monthly_aprox (int): aportación mensual aproximada al final del periodo
      - una lista de diccionarios con el resumen por año: inicio, fin y media mensual
        de cada año, todos en enteros.
    """
    if years <= 0:
        raise ValueError("years debe ser > 0")
    if annual_return < 0:
        raise ValueError("annual_return no puede ser negativo")
    if not (0.0 <= tax_rate <= 1.0):
        raise ValueError("tax_rate debe estar entre 0 y 1")

    months_total = years * 12

    def net_final_con_final_monthly(final_monthly: float) -> float:
        """Calcula el patrimonio neto al final (después de impuestos sobre plusvalías)
        para una aportación mensual final dada en un esquema lineal creciente.
        """
        val, _ = simulate_dca_ramp(
            initial_monthly=initial_monthly,
            final_monthly=final_monthly,
            years=years,
            annual_return=annual_return,
            initial_value=current_total + extra_savings,
        )
        # Suma de aportaciones en una rampa lineal: media * número de meses
        contrib_total = months_total * (initial_monthly + final_monthly) / 2.0
        principal_total = current_total + extra_savings + contrib_total
        gain = max(0.0, val - principal_total)
        tax = tax_rate * gain
        net_final = val - tax
        return net_final

    # Búsqueda binaria sobre la aportación mensual final
    low = 0.0
    high = max(initial_monthly * 10, 5000.0)
    for _ in range(30):
        mid = (low + high) / 2
        net_val = net_final_con_final_monthly(mid)
        if net_val < objetivo_final:
            low = mid
        else:
            high = mid

    final_monthly_aprox = int(round((low + high) / 2))

    # Construimos un resumen por año con aportaciones aproximadas
    resumen_anual: List[Dict[str, int]] = []
    for año in range(1, years + 1):
        start_idx = (año - 1) * 12
        end_idx = año * 12 - 1
        if end_idx >= months_total:
            end_idx = months_total - 1
        if months_total > 1:
            start_month = int(round(initial_monthly + (final_monthly_aprox - initial_monthly) * (start_idx / (months_total - 1))))
            end_month = int(round(initial_monthly + (final_monthly_aprox - initial_monthly) * (end_idx / (months_total - 1))))
        else:
            start_month = final_monthly_aprox
            end_month = final_monthly_aprox
        avg_month = int(round((start_month + end_month) / 2))
        resumen_anual.append({
            "year": año,
            "start": start_month,
            "end": end_month,
            "avg": avg_month,
        })

    return final_monthly_aprox, resumen_anual
def interactive_cli():
    print("¡Bienvenido/a! Este script te ayuda a planificar tus aportaciones mensuales para acercar tu cartera a los porcentajes objetivo mediante nuevas inversiones, y te permite simular planes de aportación creciente con diferentes escenarios de rentabilidad.")
    print()
    # Pedir número de activos
    while True:
        try:
            n_activos = int(input("¿Cuántos activos quieres introducir (por ejemplo, ETFs + Bitcoin)? "))
            if n_activos <= 0:
                print("Por favor, introduce un número positivo.")
                continue
            break
        except ValueError:
            print("Por favor, introduce un número entero.")

    holdings = {}
    targets = {}
    for i in range(n_activos):
        while True:
            nombre = input(f"Introduce el nombre del activo #{i+1}: ").strip()
            if nombre == "":
                print("El nombre no puede estar vacío.")
                continue
            if nombre in holdings:
                print("Ya has introducido ese activo. Usa un nombre único.")
                continue
            break
        while True:
            try:
                invertido = float(input(f"¿Cuánto dinero tienes invertido actualmente en '{nombre}' (en euros)? "))
                if invertido < 0:
                    print("La cantidad no puede ser negativa.")
                    continue
                break
            except ValueError:
                print("Por favor, introduce un número válido (ejemplo: 1000.50).")
        while True:
            try:
                pct = float(input(f"¿Qué porcentaje objetivo quieres para '{nombre}' (en %)? "))
                if pct < 0:
                    print("El porcentaje no puede ser negativo.")
                    continue
                break
            except ValueError:
                print("Por favor, introduce un número válido (ejemplo: 25).")
        holdings[nombre] = invertido
        targets[nombre] = pct / 100.0

    # Comprobar suma de porcentajes objetivo
    suma_objetivos = sum(targets.values())
    if not math.isclose(suma_objetivos, 1.0, abs_tol=0.01):
        print()
        print("¡Atención! La suma de los porcentajes objetivo no es 100%. Se normalizarán automáticamente.")
        for k in targets:
            targets[k] = targets[k] / suma_objetivos

    # Aportación mensual
    while True:
        try:
            monthly_contribution = float(input("¿Qué cantidad quieres aportar el próximo mes (en euros)? "))
            if monthly_contribution < 0:
                print("La cantidad no puede ser negativa.")
                continue
            break
        except ValueError:
            print("Por favor, introduce un número válido (ejemplo: 150).")

    # Umbral de rebalanceo
    while True:
        try:
            threshold_input = input("¿Umbral de rebalanceo en puntos porcentuales? (por ejemplo 2 para 2%) [0 para desactivar]: ")
            rebalance_threshold = float(threshold_input) / 100.0
            if rebalance_threshold < 0:
                print("El umbral no puede ser negativo.")
                continue
            break
        except ValueError:
            print("Por favor, introduce un número válido (ejemplo: 2).")

    portfolio = Portfolio(holdings=holdings, targets=targets)
    plan = compute_contribution_plan(
        portfolio=portfolio,
        monthly_contribution=monthly_contribution,
        rebalance_threshold=rebalance_threshold,
    )

    print("\n=== Resumen de tu cartera actual ===")
    total = portfolio.total_value()
    print(f"Valor total actual: {total:,.2f} €")
    print("Pesos actuales por activo:")
    pesos_actuales = portfolio.current_weights()
    for asset in holdings:
        print(f"  {asset:15s}: {pesos_actuales[asset]*100:6.2f} %")
    print("Pesos objetivo por activo:")
    for asset in targets:
        print(f"  {asset:15s}: {targets[asset]*100:6.2f} %")

    print("\n=== Plan de aportación para este mes ===")
    for asset, amount in plan.items():
        print(f"{asset:15s}: {amount:8d} €")

    # Nueva sección para cálculo de aportación necesaria para objetivo final
    print()
    print("Ahora puedes calcular cuánto necesitas aportar para llegar a un objetivo final en un número de años determinado, considerando una rentabilidad anual estimada.")
    simular = input("¿Quieres usar esta función? (s/n): ").strip().lower()
    if simular == "s":
        while True:
            try:
                objetivo_final = float(input("¿Cuánto dinero total te gustaría tener en la cartera en el futuro? (en euros): "))
                if objetivo_final < 0:
                    print("La cantidad no puede ser negativa.")
                    continue
                break
            except ValueError:
                print("Por favor, introduce un número válido (ejemplo: 100000).")
        while True:
            try:
                years = int(input("¿En cuántos años quieres conseguirlo? "))
                if years <= 0:
                    print("Introduce un número de años positivo.")
                    continue
                break
            except ValueError:
                print("Por favor, introduce un número entero (ejemplo: 10).")
        while True:
            try:
                annual_return_input = float(input("¿Qué rentabilidad anual aproximada quieres asumir? (por ejemplo 6, 7 u 8): "))
                if annual_return_input < 0:
                    print("La rentabilidad no puede ser negativa.")
                    continue
                annual_return = annual_return_input / 100.0
                break
            except ValueError:
                print("Por favor, introduce un número válido (ejemplo: 6).")

        modo = input("¿Quieres aportaciones constantes (c) o crecientes cada año (g)? ").strip().lower()
        if modo == "c":
            r_m = (1 + annual_return) ** (1 / 12) - 1
            months = years * 12
            valor_inicial_futuro = portfolio.total_value() * (1 + r_m) ** months
            objetivo_aportes = objetivo_final - valor_inicial_futuro
            if objetivo_aportes <= 0:
                print("Con lo que ya tienes y esa rentabilidad, no haría falta aportar (o bastaría con 0 €/mes).")
            else:
                C = objetivo_aportes * r_m / ((1 + r_m) ** months - 1)
                C_rounded = int(round(C))
                print(f"\nPara alcanzar {objetivo_final:,.2f} € en {years} años con una rentabilidad anual del {annual_return_input:.2f}%,")
                print(f"deberías aportar aproximadamente {C_rounded:d} € al mes de forma constante.")
                print("\nTabla de aportaciones constantes por año:")
                for año in range(1, years + 1):
                    print(f"Año {año:2d}: {C_rounded:d} € / mes")
        elif modo == "g":
            while True:
                try:
                    initial_monthly = float(input("¿Con cuánto te gustaría empezar aportando cada mes? (en euros): "))
                    if initial_monthly < 0:
                        print("La cantidad no puede ser negativa.")
                        continue
                    break
                except ValueError:
                    print("Por favor, introduce un número válido (ejemplo: 150).")

            def valor_final_con_final_monthly(final_monthly: float) -> float:
                val, _ = simulate_dca_ramp(
                    initial_monthly=initial_monthly,
                    final_monthly=final_monthly,
                    years=years,
                    annual_return=annual_return,
                    initial_value=portfolio.total_value(),
                )
                return val

            low = 0.0
            high = max(initial_monthly * 10, 5000.0)
            for _ in range(30):
                mid = (low + high) / 2
                val = valor_final_con_final_monthly(mid)
                if val < objetivo_final:
                    low = mid
                else:
                    high = mid
            final_monthly_aprox = int(round((low + high) / 2))
            final_value, monthly_values = simulate_dca_ramp(
                initial_monthly=initial_monthly,
                final_monthly=final_monthly_aprox,
                years=years,
                annual_return=annual_return,
                initial_value=portfolio.total_value(),
            )
            print(f"\nPara alcanzar aproximadamente {objetivo_final:,.2f} € en {years} años con rentabilidad anual del {annual_return_input:.2f}% y aportaciones crecientes,")
            print(f"deberías empezar aportando {int(round(initial_monthly))} € al mes y terminar aportando {final_monthly_aprox} € al mes.")
            print("\nTabla de aportaciones aproximadas por año:")
            months_per_year = 12
            for año in range(1, years + 1):
                start_idx = (año - 1) * months_per_year
                end_idx = año * months_per_year - 1
                if end_idx >= len(monthly_values):
                    end_idx = len(monthly_values) - 1
                # Aportación mensual al principio y al final del año (aprox)
                start_month = int(round(initial_monthly + (final_monthly_aprox - initial_monthly) * (start_idx / (years * 12 - 1)))) if years*12 > 1 else final_monthly_aprox
                end_month = int(round(initial_monthly + (final_monthly_aprox - initial_monthly) * (end_idx / (years * 12 - 1)))) if years*12 > 1 else final_monthly_aprox
                avg_month = int(round((start_month + end_month) / 2))
                print(f"Año {año:2d}: inicio ~{start_month} €, fin ~{end_month} €, media ~{avg_month} € / mes")
        else:
            print("Modo no reconocido. Por favor, elige 'c' para constante o 'g' para creciente.")


if __name__ == "__main__":
    interactive_cli()