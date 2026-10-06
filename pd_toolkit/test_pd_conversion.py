# -*- coding: utf-8 -*-
"""اختبارات pd_conversion — تشغيل: python -m unittest -v test_pd_conversion"""
import unittest

import numpy as np

import pd_conversion as pd


class TestUnits(unittest.TestCase):
    def test_dbmv_roundtrip(self):
        mv = np.array([0.01, 1.0, 10.0, 1234.5])
        np.testing.assert_allclose(pd.dbmv_to_mv(pd.mv_to_dbmv(mv)), mv)

    def test_known_values(self):
        self.assertAlmostEqual(float(pd.dbmv_to_mv(20)), 10.0)
        self.assertAlmostEqual(float(pd.dbuv_to_dbmv(80)), 20.0)
        # 0 dBm على 50 Ω = 1 mW → V_rms = sqrt(0.05) ≈ 223.6 mV
        self.assertAlmostEqual(float(pd.dbm_to_mv(0)), 223.607, places=3)

    def test_rejects_nonpositive(self):
        for bad in (0, -1, [1, 0], np.nan):
            with self.assertRaises(ValueError):
                pd.mv_to_dbmv(bad)
        with self.assertRaises(ValueError):
            pd.pc_to_tev_generic(0)


class TestGenericTEV(unittest.TestCase):
    def test_roundtrip_and_spread(self):
        q, lo, hi = pd.tev_to_pc_generic(20)
        self.assertAlmostEqual(float(q), 10_000)
        self.assertAlmostEqual(float(lo), 1_000)
        self.assertAlmostEqual(float(hi), 100_000)
        self.assertAlmostEqual(float(pd.pc_to_tev_generic(q)), 20.0)


class TestTQuantile(unittest.TestCase):
    # قيم جدولية لـ t(0.975, dof)
    TABLE = {1: 12.706, 2: 4.303, 3: 3.182, 5: 2.571, 6: 2.447, 10: 2.228, 30: 2.042}

    def test_against_table(self):
        for dof, ref in self.TABLE.items():
            self.assertAlmostEqual(pd.t_quantile(0.975, dof), ref, delta=0.005, msg=dof)

    def test_symmetry(self):
        self.assertAlmostEqual(pd.t_quantile(0.025, 6), -pd.t_quantile(0.975, 6), places=6)


class TestSiteCalibration(unittest.TestCase):
    q = np.array([20, 50, 100, 200, 500, 1000, 2000, 5000], float)

    def test_exact_linear_recovers_k(self):
        k = 2.5e-3
        cal = pd.SiteCalibration().fit(self.q, pd.mv_to_dbmv(k * self.q))
        self.assertAlmostEqual(cal.b, 1.0, places=9)
        self.assertAlmostEqual(cal.k_mv_per_pc, k, places=12)
        self.assertAlmostEqual(cal.r2, 1.0, places=9)
        qp, lo, hi = cal.predict_pc(pd.mv_to_dbmv(k * 300))
        self.assertAlmostEqual(float(qp), 300, places=6)

    def test_force_linear(self):
        y = pd.mv_to_dbmv(1e-3 * self.q) + 0.5
        cal = pd.SiteCalibration().fit(self.q, y, force_linear=True)
        self.assertEqual(cal.b, 1.0)
        self.assertAlmostEqual(cal.a, -60.0 + 0.5, places=9)
        self.assertEqual(cal.dof, len(self.q) - 1)

    def test_predict_dbmv_inverse(self):
        rng = np.random.default_rng(0)
        y = pd.mv_to_dbmv(2e-3 * self.q) + rng.normal(0, 1, self.q.size)
        cal = pd.SiteCalibration().fit(self.q, y)
        qp, _, _ = cal.predict_pc(cal.predict_dbmv(777.0))
        self.assertAlmostEqual(float(qp), 777.0, places=6)

    def test_interval_wider_when_extrapolating(self):
        rng = np.random.default_rng(1)
        y = pd.mv_to_dbmv(2.5e-3 * self.q) + rng.normal(0, 1.5, self.q.size)
        cal = pd.SiteCalibration().fit(self.q, y)
        def width_db(reading):
            _, lo, hi = cal.predict_pc(reading)
            return 20 * np.log10(hi / lo)
        center = cal.a + cal.b * cal.xbar
        self.assertLess(width_db(center), width_db(center + 20))

    def test_interval_coverage(self):
        """مجال 95% يجب أن يحتوي الشحنة الحقيقية في ~95% من التجارب."""
        rng = np.random.default_rng(42)
        k, sigma, q_true, trials, hits = 2.5e-3, 1.5, 3000.0, 2000, 0
        for _ in range(trials):
            y = pd.mv_to_dbmv(k * self.q) + rng.normal(0, sigma, self.q.size)
            cal = pd.SiteCalibration().fit(self.q, y)
            reading = pd.mv_to_dbmv(k * q_true) + rng.normal(0, sigma)
            _, lo, hi = cal.predict_pc(reading)
            hits += lo <= q_true <= hi
        self.assertAlmostEqual(hits / trials, 0.95, delta=0.02)

    def test_validation(self):
        cal = pd.SiteCalibration()
        with self.assertRaises(ValueError):
            cal.fit([10, 20], [1, 2])                 # نقطتان لا تكفيان للميل
        with self.assertRaises(ValueError):
            cal.fit([10, 10, 10], [1, 2, 3])          # ميل غير قابل للتقدير
        with self.assertRaises(ValueError):
            cal.fit([10, 0, 30], [1, 2, 3])           # شحنة صفرية
        with self.assertRaises(ValueError):
            cal.fit([10, 20, 30], [1, 2])             # أطوال مختلفة
        cal.fit([10, 20], [1, 7], force_linear=True)  # مسموح مع force_linear


class TestHFCT(unittest.TestCase):
    def test_gaussian_pulse_charge(self):
        dt = 0.5; t = np.arange(0, 400, dt)
        i_ma = 2.0 * np.exp(-((t - 150) / 10) ** 2)
        expected = 2.0 * 10 * np.sqrt(np.pi)             # ∫ = A·w·√π
        Zs = 7.0
        u = i_ma * Zs + 3.0                              # إزاحة DC يجب أن تُزال
        self.assertAlmostEqual(pd.hfct_charge_pc(u, dt, Zs), expected, places=6)

    def test_scale_factor(self):
        self.assertEqual(pd.hfct_scale_factor_pc_per_mv(75, 15), 5.0)


class TestIEC60270(unittest.TestCase):
    def test_peak(self):
        self.assertAlmostEqual(float(pd.iec60270_peak_mv(100, 100e3, 400e3, 1000)), 60.0)

    def test_q_equals_cv(self):
        self.assertEqual(float(pd.apparent_charge_from_capacitance(10, 1)), 10.0)


class TestUHF(unittest.TestCase):
    def test_energy_of_constant_signal(self):
        # 100 mV ثابتة لمدة 10 ns على 50 Ω → (0.1²/50)·10e-9 = 2e-12 J
        self.assertAlmostEqual(pd.uhf_energy(np.full(10, 100.0), 1.0), 2e-12, places=20)

    def test_fit_exact(self):
        q = np.array([5, 10, 20, 50, 100], float)
        f = pd.UHFEnergyFit().fit(q, 3e-15 * q ** 2)
        self.assertAlmostEqual(f.c / 3e-15, 1.0, places=9)
        np.testing.assert_allclose(f.predict_pc(3e-15 * q ** 2), q)

    def test_negative_energy_rejected(self):
        f = pd.UHFEnergyFit().fit([1, 2, 3], [1e-15, 4e-15, 9e-15])
        with self.assertRaises(ValueError):
            f.predict_pc(-1e-15)


if __name__ == "__main__":
    unittest.main()
