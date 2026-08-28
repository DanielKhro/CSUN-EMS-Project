"""
Jetson-friendly, single-file, realtime EMS controller.
- Decisions every 15 minutes (dtHours=0.25)
- Keeps controller state (SOC, mode, dwell, last Pbatt) across steps
"""
from __future__ import annotations
import time
import random
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

# ==========================================
# HARDWARE & BACKUP PARAMETERS
# ==========================================
@dataclass
class BatteryParams:
    Emax_kWh: float = 5.12
    Vnom_V: float = 51.2
    Ichg_max_A: float = 50.0
    Pchg_max_kW: float = (51.2 * 50.0) / 1000.0  # 2.56 kW
    Pdis_max_kW: float = 4.0
    eta_c: float = 0.95
    eta_d: float = 0.95
    SOC_min: float = 0.20
    SOC_max: float = 0.90
    SOC0: float = 0.50  
    minDwellSteps: int = 4
    ramp_kW_perStep: float = 0.5

@dataclass
class BackupParams:
    backup_enabled: bool = True
    SOC_reserve_backup: float = 0.30
    allow_load_shed: bool = True
    recover_steps_required: int = 2

# ==========================================
# LADWP TOU PRICING LOGIC
# ==========================================
def ladwp_r1b_prices_for_month(day: date) -> Dict[str, float]:
    m = day.month
    if m in (1, 2, 3): return {"high": 0.25172, "low": 0.25172, "base": 0.22818}
    elif m in (4, 5): return {"high": 0.25641, "low": 0.25641, "base": 0.23287}
    elif m == 6: return {"high": 0.31481, "low": 0.25641, "base": 0.22897}
    elif m in (7, 8, 9): return {"high": 0.33022, "low": 0.27182, "base": 0.24438}
    else: return {"high": 0.27480, "low": 0.27480, "base": 0.25126}

def ladwp_thresholds_from_month(day: date) -> Dict[str, Any]:
    rates = ladwp_r1b_prices_for_month(day)
    spread = max(rates["high"] - rates["base"], 1e-6)
    return {
        "pChg_on":  rates["base"] + (0.10 * spread),
        "pChg_off": rates["base"] + (0.25 * spread),
        "pDis_on":  rates["high"] - (0.20 * spread),
        "pDis_off": rates["high"] - (0.40 * spread),
        "prefer_grid_in_low": True,
        "low_band": (rates["low"] - (0.02 * spread), rates["low"] + (0.02 * spread)),
        "rates": rates,
    }

def ladwp_price_for_time(now: datetime) -> Dict[str, Any]:
    rates = ladwp_r1b_prices_for_month(now.date())
    is_weekend = (now.weekday() >= 5)
    h = now.hour + (now.minute / 60.0)

    if is_weekend: return {"price": rates["base"], "period": "BASE"}
    if 13.0 <= h < 17.0: return {"price": rates["high"], "period": "HIGH"}
    elif (10.0 <= h < 13.0) or (17.0 <= h < 20.0): return {"price": rates["low"], "period": "LOW"}
    else: return {"price": rates["base"], "period": "BASE"}

# ==========================================
# STATEFUL REALTIME CONTROLLER
# ==========================================
class EMSController:
    def __init__(self, dtHours: float = 0.25, p: Optional[BatteryParams] = None, b: Optional[BackupParams] = None):
        self.dtHours = dtHours
        self.p = p or BatteryParams()
        self.b = b or BackupParams()
        self.mode = "GRID"
        self.dwell = self.p.minDwellSteps
        self.Pbatt_last = 0.0
        self.soc_kWh = self.p.SOC0 * self.p.Emax_kWh
        self._thr_day: Optional[date] = None
        self._thr: Optional[Dict[str, Any]] = None

    def _get_thr(self, day: date) -> Dict[str, Any]:
        if self._thr_day != day or self._thr is None:
            self._thr_day = day
            self._thr = ladwp_thresholds_from_month(day)
        return self._thr

    def step(self, now: datetime, load_kW: float, grid_ok: int, soc_kWh_meas: Optional[float] = None) -> Dict[str, Any]:
        p = self.p
        b = self.b

        if soc_kWh_meas is not None:
            self.soc_kWh = float(soc_kWh_meas)

        soc_min_kWh = p.SOC_min * p.Emax_kWh
        soc_max_kWh = p.SOC_max * p.Emax_kWh
        self.soc_kWh = max(soc_min_kWh, min(soc_max_kWh, self.soc_kWh))
        soc = self.soc_kWh / p.Emax_kWh

        tou = ladwp_price_for_time(now)
        price = tou["price"]
        period = tou["period"]
        thr = self._get_thr(now.date())

        outage = (b.backup_enabled and int(grid_ok) == 0)
        reason = "TOU"
        desired = self.mode
        Pbatt_target = 0.0

        if outage:
            reason = "BACKUP"
            SOC_reserve = max(b.SOC_reserve_backup, p.SOC_min)
            if (soc <= SOC_reserve) and b.allow_load_shed:
                desired = "LOAD_SHED"
                reason = "BACKUP_RESERVE"
                Pbatt_target = 0.0
            else:
                desired = "DISCHARGE"
                Pbatt_target = -p.Pdis_max_kW
            self.mode = desired
            self.dwell = 0  
        else:
            can_switch = (self.dwell >= p.minDwellSteps)
            if self.mode == "LOAD_SHED":
                desired = "GRID"
            elif self.mode == "DISCHARGE":
                if can_switch and ((price < thr["pDis_off"]) or (soc <= p.SOC_min)): desired = "GRID"
            elif self.mode == "CHARGE":
                if can_switch and ((price > thr["pChg_off"]) or (soc >= p.SOC_max)): desired = "GRID"
            else:  
                in_low_neutral = False
                if thr.get("prefer_grid_in_low", False):
                    lo, hi = thr["low_band"]
                    in_low_neutral = (lo <= price <= hi)
                if can_switch and not in_low_neutral:
                    if (price >= thr["pDis_on"]) and (soc > p.SOC_min + 0.02): desired = "DISCHARGE"
                    elif (price <= thr["pChg_on"]) and (soc < p.SOC_max - 0.02): desired = "CHARGE"

            if desired != self.mode:
                self.mode = desired
                self.dwell = 0
            else:
                self.dwell += 1

            if (self.mode == "CHARGE") and (soc < p.SOC_max): Pbatt_target = +p.Pchg_max_kW
            elif (self.mode == "DISCHARGE") and (soc > p.SOC_min): Pbatt_target = -p.Pdis_max_kW

        delta = Pbatt_target - self.Pbatt_last
        delta = max(-p.ramp_kW_perStep, min(p.ramp_kW_perStep, delta))
        Pbatt = self.Pbatt_last + delta
        Pbatt = max(-p.Pdis_max_kW, min(p.Pchg_max_kW, Pbatt))
        self.Pbatt_last = Pbatt

        if outage: Pgrid = 0.0
        else:
            Pgrid = float(load_kW) + max(Pbatt, 0.0) - max(-Pbatt, 0.0)
            Pgrid = max(Pgrid, 0.0)

        if Pbatt >= 0.0: self.soc_kWh += (Pbatt * p.eta_c) * self.dtHours
        else: self.soc_kWh += (Pbatt / p.eta_d) * self.dtHours
        self.soc_kWh = max(soc_min_kWh, min(soc_max_kWh, self.soc_kWh))

        return {
            "timestamp": now,
            "mode": self.mode,
            "Pbatt_kW": Pbatt,
            "Pgrid_kW": Pgrid,
            "SOC_kWh": self.soc_kWh,
            "reason": reason,
            "tou_period": period,
            "price": price,
            "grid_ok": int(grid_ok),
            "load_kW": float(load_kW),
        }