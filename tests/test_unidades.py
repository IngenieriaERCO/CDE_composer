import pytest

from componedor.unidades import mm_a_pt, pt_a_mm


def test_una_pulgada():
    assert mm_a_pt(25.4) == pytest.approx(72.0)
    assert pt_a_mm(72.0) == pytest.approx(25.4)


def test_ida_y_vuelta():
    for mm in (0.0, 1.0, 12.7, 594.0, 841.0):
        assert pt_a_mm(mm_a_pt(mm)) == pytest.approx(mm)
