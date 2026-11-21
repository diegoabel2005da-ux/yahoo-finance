"""Convenciones de fechas, calendario y calendarios de pago (sección 12).

El calendario mexicano se construye por reglas (LFT art. 74 y días inhábiles habituales del
mercado). Es una APROXIMACIÓN: el calendario oficial de BMV/Banxico/MexDer de cada año debe
importarse para producción (`HolidayCalendar.from_dates`) y prevalece sobre las reglas.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from dateutil.relativedelta import relativedelta


def easter(year: int) -> date:
    """Algoritmo gregoriano anónimo (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _nth_weekday(year, month, weekday, n):
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def mexican_market_holidays(year: int) -> set[date]:
    e = easter(year)
    return {
        date(year, 1, 1),
        _nth_weekday(year, 2, 0, 1),     # Constitución: primer lunes de febrero
        _nth_weekday(year, 3, 0, 3),     # Natalicio de Juárez: tercer lunes de marzo
        e - timedelta(days=3),           # Jueves santo
        e - timedelta(days=2),           # Viernes santo
        date(year, 5, 1),
        date(year, 9, 16),
        date(year, 11, 2),
        _nth_weekday(year, 11, 0, 3),    # Revolución: tercer lunes de noviembre
        date(year, 12, 12),
        date(year, 12, 25),
    }


@dataclass
class HolidayCalendar:
    name: str = "MX-reglas"
    explicit: set[date] = field(default_factory=set)
    use_rules: bool = True
    source: str = "Reglas LFT art. 74 + inhábiles habituales (aproximación, verificar calendario oficial)"

    @classmethod
    def from_dates(cls, dates: list[date], name: str, source: str) -> "HolidayCalendar":
        return cls(name=name, explicit=set(dates), use_rules=False, source=source)

    def is_holiday(self, d: date) -> bool:
        if d in self.explicit:
            return True
        return self.use_rules and d in mexican_market_holidays(d.year)

    def is_business_day(self, d: date) -> bool:
        return d.weekday() < 5 and not self.is_holiday(d)

    def adjust(self, d: date, rule: str = "modified_following") -> date:
        if rule == "none":
            return d
        if rule in ("following", "modified_following"):
            x = d
            while not self.is_business_day(x):
                x += timedelta(days=1)
            if rule == "modified_following" and x.month != d.month:
                return self.adjust(d, "preceding")
            return x
        if rule == "preceding":
            x = d
            while not self.is_business_day(x):
                x -= timedelta(days=1)
            return x
        raise ValueError(f"regla de ajuste desconocida: {rule}")

    def add_business_days(self, d: date, n: int) -> date:
        step = 1 if n >= 0 else -1
        x, k = d, 0
        while k < abs(n):
            x += timedelta(days=step)
            if self.is_business_day(x):
                k += 1
        return x

    def business_days_between(self, start: date, end: date) -> list[date]:
        out, x = [], start
        while x < end:
            if self.is_business_day(x):
                out.append(x)
            x += timedelta(days=1)
        return out


def year_fraction(d1: date, d2: date, convention: str) -> float:
    """Fracción de año entre dos fechas."""
    days = (d2 - d1).days
    c = convention.upper()
    if c in ("ACT/360", "A360"):
        return days / 360.0
    if c in ("ACT/365F", "ACT/365", "A365F"):
        return days / 365.0
    if c in ("30/360", "30/360US", "30U/360"):
        y1, m1, dd1 = d1.year, d1.month, d1.day
        y2, m2, dd2 = d2.year, d2.month, d2.day
        if dd1 == 31:
            dd1 = 30
        if dd2 == 31 and dd1 == 30:
            dd2 = 30
        return (360 * (y2 - y1) + 30 * (m2 - m1) + (dd2 - dd1)) / 360.0
    if c in ("30E/360",):
        dd1, dd2 = min(d1.day, 30), min(d2.day, 30)
        return (360 * (d2.year - d1.year) + 30 * (d2.month - d1.month) + (dd2 - dd1)) / 360.0
    raise ValueError(f"convención de días no soportada: {convention}")


@dataclass
class Period:
    accrual_start: date
    accrual_end: date
    fixing_date: date
    payment_date: date
    notional: float
    accrual: float


def build_schedule(start: date, end: date, frequency: str, notional: float, day_count: str = "ACT/360",
                   calendar: HolidayCalendar | None = None, adjust_rule: str = "modified_following",
                   fixing_lag_bd: int = 1, payment_lag_bd: int = 0,
                   amortization: list[float] | None = None) -> list[Period]:
    """Calendario de periodos.

    frequency: '28D' (TIIE 28 típica), '91D', '182D', '1M', '3M', '6M', '12M'.
    amortization: nocional vigente por periodo (si se omite, constante).
    fixing_lag_bd: días hábiles de anticipación de la fijación respecto del inicio
    (para tasas fijadas al inicio). Para tasas compuestas en atraso la tasa se observa
    durante el periodo y `fixing_date` se iguala al fin del periodo.
    """
    cal = calendar or HolidayCalendar()
    unit = frequency[-1].upper()
    qty = int(frequency[:-1])
    unadj = [start]
    k = 1
    while True:
        nxt = start + (timedelta(days=qty * k) if unit == "D" else relativedelta(months=qty * k))
        if nxt >= end:
            break
        unadj.append(nxt)
        k += 1
    unadj.append(end)
    adj = [unadj[0]] + [cal.adjust(d, adjust_rule) for d in unadj[1:]]
    n = len(adj) - 1
    if amortization is not None and len(amortization) != n:
        raise ValueError(f"amortization debe tener {n} elementos (uno por periodo)")
    out = []
    for i in range(n):
        s, e = adj[i], adj[i + 1]
        out.append(Period(
            accrual_start=s, accrual_end=e,
            fixing_date=cal.add_business_days(s, -fixing_lag_bd) if fixing_lag_bd else s,
            payment_date=cal.add_business_days(e, payment_lag_bd) if payment_lag_bd else e,
            notional=amortization[i] if amortization else notional,
            accrual=year_fraction(s, e, day_count),
        ))
    return out


def compounded_in_arrears(fixings: dict[date, float], start: date, end: date, calendar: HolidayCalendar,
                          day_basis: float = 360.0) -> dict:
    """Tasa overnight compuesta en atraso (p. ej. TIIE de Fondeo compuesta):

    R = [Π_i (1 + r_i·d_i/360) − 1] · 360 / D

    r_i: tasa publicada del día hábil i (decimal); d_i: días naturales hasta el siguiente hábil;
    D: días naturales del periodo. Exige fijación para CADA día hábil (no se rellenan faltantes).
    """
    days = calendar.business_days_between(start, end)
    missing = [d for d in days if d not in fixings]
    if missing:
        return {"rate": None, "missing_fixings": missing,
                "error": f"faltan {len(missing)} fijaciones; no se rellenan valores"}
    factor = 1.0
    for i, d in enumerate(days):
        nxt = days[i + 1] if i + 1 < len(days) else end
        factor *= 1 + fixings[d] * (nxt - d).days / day_basis
    D = (end - start).days
    return {"rate": (factor - 1) * day_basis / D, "factor": factor, "business_days": len(days), "days": D}
