"""Statistics must describe the successful samples, including timeout counts."""
import math
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from modules import akarius_sim as akarius
from modules import alternox_prime_sim as alternox
from modules import jat_kittag_sim as jat
from modules import kuva_nukor_sim as nukor
from modules import ocucor_sim as ocucor
from modules.trial_statistics import sample_percentile


class PercentileTests(unittest.TestCase):
    def test_sort_and_interpolate(self):
        self.assertEqual(sample_percentile([4, 1, 3, 2], 0.5), 2.5)
        self.assertAlmostEqual(sample_percentile([4, 1, 3, 2], 0.9), 3.7)
        self.assertEqual(sample_percentile([9], 0.9), 9)
        # Keep the established JSON representation for interpolated integer
        # counts even when both neighboring samples have the same value.
        self.assertIsInstance(sample_percentile([3, 3], 0.5), float)
        self.assertIsInstance(sample_percentile([3, 3], 0), int)
        self.assertTrue(math.isnan(sample_percentile([], 0.5)))
        self.assertTrue(math.isinf(sample_percentile([], 0.5, empty=math.inf)))
        with self.assertRaises(ValueError):
            sample_percentile([1], 1.01)

    def test_interpolation_with_infinite_endpoints(self):
        self.assertEqual(sample_percentile([math.inf, math.inf], 0.5), math.inf)
        self.assertEqual(sample_percentile([-math.inf, -math.inf], 0.5), -math.inf)
        self.assertEqual(sample_percentile([1.0, math.inf], 0.5), math.inf)
        self.assertEqual(sample_percentile([-math.inf, 1.0], 0.5), -math.inf)
        self.assertTrue(math.isnan(sample_percentile([-math.inf, math.inf], 0.5)))
        self.assertEqual(sample_percentile([-math.inf, math.inf], 0), -math.inf)
        self.assertEqual(sample_percentile([-math.inf, math.inf], 1), math.inf)

    def test_finite_endpoints_do_not_overflow_during_interpolation(self):
        self.assertEqual(sample_percentile([-1e308, 1e308], 0.5), 0)
        self.assertEqual(sample_percentile([-1e308, 1e308], 0.25), -5e307)
        self.assertEqual(sample_percentile([-1e308, 1e308], 0.75), 5e307)

    def test_nan_samples_are_rejected_rather_than_sorted_ambiguously(self):
        for values in ([math.nan], [1, math.nan, 3]):
            with self.subTest(values=values), self.assertRaisesRegex(ValueError, "NaN"):
                sample_percentile(values, 0.5)


class TrialSummaryTests(unittest.TestCase):
    @staticmethod
    def result(ttk, value):
        return SimpleNamespace(
            ttk=ttk, overguard_break_time=value, final_armor=value * 100,
            reloads=value, shots=value, flare_stacks_peak=value,
            affliction_triggers=value, slams=value, combo_tiers=[value],
            final_viral_stacks=value,
        )

    def cases(self):
        return (
            (nukor, lambda n: nukor.run_trials("Frostbite", trials=n),
             "final_armor_median"),
            (ocucor, lambda n: ocucor.run_trials(ocucor.ARCANE_ENERVATE, "Damage", trials=n),
             "armor_median"),
            (akarius, lambda n: akarius.run_trials(akarius.RIVEN_VIRAL, trials=n),
             "armor_median"),
            (jat, lambda n: jat.run_trials("Riven MD+CD", trials=n),
             "armor_median"),
            (alternox, lambda n: alternox.run_trials(
                (alternox.R_BLAST, alternox.R_DAMAGE, alternox.R_TOXIN), trials=n),
             None),
        )

    def test_unsorted_samples_and_timeouts_are_reported(self):
        samples = [self.result(3, 9), self.result(1, 1), self.result(2, 5),
                   self.result(math.inf, 999)]
        for module, run, armor_key in self.cases():
            with self.subTest(module=module.__name__), \
                 patch.object(module, "simulate", side_effect=samples):
                report = run(4)
                self.assertEqual(report["trials"], 3)
                self.assertEqual(report["trials_attempted"], 4)
                self.assertEqual(report["timed_out"], 1)
                self.assertEqual(report["ttk_median"], 2)
                self.assertEqual(report["ttk_mean"], 2)
                self.assertAlmostEqual(report["ttk_p90"], 2.8)
                if armor_key:
                    self.assertEqual(report[armor_key], 500)
                if module is not alternox:
                    self.assertEqual(report["overguard_median"], 5)
                if module is ocucor:
                    self.assertEqual(report["flare_peak_median"], 5)
                if module is akarius:
                    self.assertEqual(report["shots_mean"], 5)
                    self.assertEqual(report["first_magazine_kills"], 0)
                if module is jat:
                    self.assertEqual(report["affliction_median"], 5)
                    self.assertEqual(report["slams_median"], 5)
                if module is alternox:
                    self.assertEqual(report["reloads_median"], 5)
                    self.assertEqual(report["viral_median"], 5)

    def test_infinite_observed_metric_does_not_turn_into_nan(self):
        # The generic reporter accepts supplied trial results; this does not
        # imply normal successful kills have an infinite Overguard break time.
        samples = [self.result(1, math.inf), self.result(2, math.inf)]
        with patch.object(nukor, "simulate", side_effect=samples):
            report = nukor.run_trials("Frostbite", trials=2)
        self.assertEqual(report["overguard_median"], math.inf)
        self.assertEqual(report["final_armor_median"], math.inf)
        self.assertEqual(report["ttk_median"], 1.5)

    def test_all_timeouts_do_not_crash(self):
        for module, run, armor_key in self.cases():
            with self.subTest(module=module.__name__), \
                 patch.object(module, "simulate", return_value=self.result(math.inf, 99)):
                report = run(2)
                self.assertEqual(report["trials"], 0)
                self.assertEqual(report["trials_attempted"], 2)
                self.assertEqual(report["timed_out"], 2)
                self.assertTrue(math.isinf(report["ttk_median"]))
                if module is akarius:
                    self.assertTrue(math.isnan(report["shots_mean"]))
                    self.assertEqual(report["first_magazine_kills"], 0)
                if armor_key:
                    self.assertTrue(math.isnan(report[armor_key]))
                else:
                    self.assertTrue(math.isnan(report["viral_median"]))

    def test_zero_trials_is_rejected(self):
        for module, run, _ in self.cases():
            with self.subTest(module=module.__name__), self.assertRaises(ValueError):
                run(0)


if __name__ == "__main__":
    unittest.main()
