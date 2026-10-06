# -*- coding: utf-8 -*-
"""
أدوات تحويل وتقدير بين الشحنة الظاهرية (pC) وقراءات الحساسات (mV / dBmV / UHF)
PD conversion toolkit: pC <-> mV/dBmV, site calibration, HFCT integration, UHF energy fit.

تنبيه: التحويل العام (بدون معايرة) تقدير بترتيب المقدار فقط.
التحويل الموثوق يحتاج معايرة في نفس المعدّة ونفس موضع الحساس ونفس الجهاز.
"""
import math
from statistics import NormalDist

import numpy as np

# np.trapezoid أُضيفت في NumPy 2.0، وnp.trapz أُزيلت لاحقًا — ندعم الاثنين
_trapezoid = getattr(np, "trapezoid", None) or np.trapz

def _positive(x, name):
    """يرفض القيم الصفرية أو السالبة قبل أخذ اللوغاريتم أو الجذر."""
    x = np.asarray(x, float)
    if np.any(~np.isfinite(x)) or np.any(x <= 0):
        raise ValueError(f"{name} يجب أن تكون قيمًا موجبة ومحدودة")
    return x

def t_quantile(p, dof):
    """مقلوب توزيع t لستيودنت. يستخدم scipy إن وُجد، وإلا صيغًا مغلقة دقيقة
    لـ dof=1,2 وتوسعة Cornish-Fisher (Abramowitz & Stegun 26.7.5) لـ dof≥3
    (خطأ < 0.005 عند 95%)."""
    try:
        from scipy.stats import t
        return float(t.ppf(p, dof))
    except ImportError:
        pass
    if dof == 1:
        return math.tan(math.pi * (p - 0.5))
    if dof == 2:
        return (2 * p - 1) / math.sqrt(2 * p * (1 - p))
    z = NormalDist().inv_cdf(p); v = dof
    g1 = (z**3 + z) / 4
    g2 = (5*z**5 + 16*z**3 + 3*z) / 96
    g3 = (3*z**7 + 19*z**5 + 17*z**3 - 15*z) / 384
    g4 = (79*z**9 + 776*z**7 + 1482*z**5 - 1920*z**3 - 945*z) / 92160
    return z + g1/v + g2/v**2 + g3/v**3 + g4/v**4

# ---------- 1) الوحدات ----------
def dbmv_to_mv(dbmv):            return 10 ** (np.asarray(dbmv, float) / 20.0)
def mv_to_dbmv(mv):              return 20 * np.log10(_positive(mv, "mV"))
def dbuv_to_dbmv(dbuv):          return np.asarray(dbuv, float) - 60.0
def dbm_to_mv(dbm, R=50.0):      # قدرة dBm على حمل R إلى جهد RMS بالميلي فولت
    p_w = 1e-3 * 10 ** (np.asarray(dbm, float) / 10.0); return np.sqrt(p_w * R) * 1e3

# ---------- 2) تقدير عام TEV -> pC (Reid, Judd, Duncan 2012) ----------
A_REID_MV_PER_PC = 1e-3   # ≈ 1 µV/pC ميل تقريبي لبيانات أربع خلايا مخبرية مجتمعة

def tev_to_pc_generic(dbmv, A=A_REID_MV_PER_PC, spread_factor=10.0):
    """q ≈ 10^(dBmV/20) / A . يعيد (q, q_low, q_high).
    spread_factor افتراض توضيحي لتشتت بترتيب مقدار بين أنواع العيوب، وليس قيمة منشورة."""
    q = dbmv_to_mv(dbmv) / A
    return q, q / spread_factor, q * spread_factor

def pc_to_tev_generic(q_pc, A=A_REID_MV_PER_PC):
    return mv_to_dbmv(_positive(q_pc, "q_pC") * A)

# ---------- 3) معايرة خاصة بالموقع (الطريقة الموصى بها) ----------
class SiteCalibration:
    """نموذج لوغاريتمي: dBmV = a + b * 20*log10(q_pC)
    b = 1 يعني تناسبًا خطيًا V = k*q . يُبنى من قياسات متزامنة (IEC 60270 + TEV)
    أو من حقن شحنات معلومة عند نفس النقطة.
    ملاحظة: مع force_linear=True قد يكون R² سالبًا، وهذا يعني أن فرض b=1
    أسوأ من مجرد المتوسط — أي أن البيانات لا تتبع تناسبًا خطيًا."""
    def fit(self, q_pc, reading_dbmv, force_linear=False):
        x = 20 * np.log10(_positive(q_pc, "q_pC")); y = np.asarray(reading_dbmv, float)
        n = len(x)
        if y.shape != x.shape:
            raise ValueError("q_pc و reading_dbmv يجب أن يكونا بنفس الطول")
        if n < (2 if force_linear else 3):
            raise ValueError("نقاط المعايرة غير كافية (≥2 مع force_linear، وإلا ≥3)")
        if not force_linear and np.ptp(x) == 0:
            raise ValueError("كل الشحنات متساوية — لا يمكن تقدير الميل")
        if force_linear:
            self.b = 1.0; self.a = float(np.mean(y - x))
        else:
            self.b, self.a = np.polyfit(x, y, 1)
        yhat = self.a + self.b * x; res = y - yhat
        dof = n - (1 if force_linear else 2); self.dof = dof
        self.s = float(np.sqrt(np.sum(res**2) / dof))
        self.r2 = float(1 - np.sum(res**2) / np.sum((y - y.mean())**2)) if n > 2 else float("nan")
        self.k_mv_per_pc = 10 ** (self.a / 20)          # ثابت التحويل عند b=1
        self.n = n; self.xbar = x.mean(); self.sxx = np.sum((x - x.mean())**2); self.force = force_linear
        return self
    def predict_dbmv(self, q_pc):
        return self.a + self.b * 20 * np.log10(_positive(q_pc, "q_pC"))
    def predict_pc(self, reading_dbmv, conf=0.95):
        """عكس النموذج مع مجال تنبؤ تقريبي (افتراضيًا 95%).
        يشمل تشتت البواقي وعدم اليقين في معاملات الملاءمة، ويستخدم توزيع t
        لأن σ مقدَّرة من عدد قليل من النقاط. المجال يتسع كلما ابتعدت القراءة
        عن مركز بيانات المعايرة (الاستقراء خارج المدى أقل موثوقية)."""
        y = np.asarray(reading_dbmv, float)
        x = (y - self.a) / self.b
        t = t_quantile(0.5 + conf / 2, self.dof)
        if self.force:                       # معامل واحد (a) فقط مقدَّر
            se = self.s * np.sqrt(1 + 1 / self.n)
        else:
            se = self.s * np.sqrt(1 + 1 / self.n + (x - self.xbar) ** 2 / self.sxx)
        dx = t * se / abs(self.b)
        q = 10 ** (x / 20); return q, 10 ** ((x - dx) / 20), 10 ** ((x + dx) / 20)
    def report(self):
        return (f"dBmV = {self.a:.2f} + {self.b:.3f}·20log10(q)   R²={self.r2:.3f}   "
                f"σ={self.s:.2f} dB   n={self.n}   k≈{self.k_mv_per_pc*1e3:.3f} µV/pC (عند b=1)")

# ---------- 4) HFCT: تكامل نبضة التيار ----------
def hfct_charge_pc(u_mv, dt_ns, Zs_mv_per_ma, baseline_pts=50):
    """q = ∫ i dt = ∫ u/Zs dt . u بالميلي فولت، dt بالنانوثانية، Zs بـ mV/mA (=Ω).
    الناتج: mA·ns = pC."""
    u = np.asarray(u_mv, float); u = u - np.median(u[:baseline_pts])
    return float(_trapezoid(u, dx=dt_ns) / Zs_mv_per_ma)

def hfct_scale_factor_pc_per_mv(T_pd_ns, Zs_mv_per_ma):
    """k = T_PD / Zs (Khamlichi وآخرون 2023) بشرط ثبات Zs على طيف النبضة."""
    return T_pd_ns / Zs_mv_per_ma

# ---------- 5) دائرة IEC 60270 ----------
def iec60270_peak_mv(q_pc, f1_hz, f2_hz, Zm_ohm):
    """u_peak = 2 (f2 - f1) Zm q  (نطاق تمرير مسطح)."""
    return 2 * (f2_hz - f1_hz) * Zm_ohm * np.asarray(q_pc, float) * 1e-12 * 1e3

def apparent_charge_from_capacitance(delta_v_mv, C_nF):
    """q = C·ΔV  →  pC = nF × mV . مثال CIRED 2019: 1 nF و10 mV ↔ 10 pC."""
    return np.asarray(C_nF, float) * np.asarray(delta_v_mv, float)

# ---------- 6) UHF: الطاقة ∝ q² ----------
def uhf_energy(u_mv, dt_ns, R=50.0):
    u = np.asarray(u_mv, float) * 1e-3; return float(np.sum(u**2) * dt_ns * 1e-9 / R)   # جول
class UHFEnergyFit:
    """E = c·q²  ⇒  q = sqrt(E/c) . يُبنى لكل نوع عيب وكل موضع حساس."""
    def fit(self, q_pc, E):
        q2 = _positive(q_pc, "q_pC")**2; E = np.asarray(E, float)
        if np.any(E < 0): raise ValueError("الطاقة لا يمكن أن تكون سالبة")
        self.c = float(np.sum(q2 * E) / np.sum(q2**2))
        res = E - self.c * q2; self.r2 = float(1 - np.sum(res**2) / np.sum((E - E.mean())**2)); return self
    def predict_pc(self, E):
        E = np.asarray(E, float)
        if np.any(E < 0): raise ValueError("الطاقة لا يمكن أن تكون سالبة")
        return np.sqrt(E / self.c)

# ---------- عرض توضيحي ----------
if __name__ == "__main__":
    print("1) أمثلة الوحدات:", dbmv_to_mv(20), "mV ;", dbuv_to_dbmv(80), "dBmV")
    for d in [15, 20, 40]:
        q, lo, hi = tev_to_pc_generic(d)
        print(f"2) تقدير عام: {d} dBmV → ≈{q:,.0f} pC  (مجال توضيحي {lo:,.0f} – {hi:,.0f})")
    # بيانات معايرة صناعية للتجربة فقط
    rng = np.random.default_rng(1)
    q = np.array([20, 50, 100, 200, 500, 1000, 2000, 5000])
    true_k = 2.5e-3                                    # mV/pC افتراضي لهذه اللوحة
    y = mv_to_dbmv(true_k * q) + rng.normal(0, 1.5, q.size)
    cal = SiteCalibration().fit(q, y)
    print("3) معايرة موقع (بيانات تجريبية):", cal.report())
    qp, ql, qh = cal.predict_pc(30)
    print(f"   قراءة 30 dBmV → q ≈ {qp:,.0f} pC  (95%: {ql:,.0f} – {qh:,.0f})")
    # HFCT
    dt = 1.0; t = np.arange(0, 400, dt)
    i_ma = 1.0 * np.exp(-((t - 100) / 20) ** 2)        # نبضة تيار ذروتها 1 mA
    Zs = 5.0
    print(f"4) HFCT: q المحسوبة = {hfct_charge_pc(i_ma * Zs, dt, Zs):.1f} pC (القيمة الصحيحة {_trapezoid(i_ma, dx=dt):.1f})")
    print("   معامل المقياس k = T_PD/Zs =", hfct_scale_factor_pc_per_mv(75, 15), "pC/mV")
    print("5) IEC 60270: 100 pC، 100–400 kHz، Zm=1 kΩ → u_peak =", round(float(iec60270_peak_mv(100, 100e3, 400e3, 1000)), 3), "mV")
    print("   q = C·ΔV: 1 nF × 10 mV =", apparent_charge_from_capacitance(10, 1), "pC")
    qq = np.array([5, 10, 20, 50, 100]); E = 3e-15 * qq**2 * (1 + rng.normal(0, .05, qq.size))
    f = UHFEnergyFit().fit(qq, E); print(f"6) UHF: E=c·q²، R²={f.r2:.3f} ، طاقة {E[2]:.2e} J → {float(f.predict_pc(E[2])):.1f} pC")
