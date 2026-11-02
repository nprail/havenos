from havenos.core.qr import matrix


def test_matrix_is_a_square_of_zeros_and_ones():
    rows = matrix("http://192.0.2.10:8787/?code=ABCD-2345")
    assert len(rows) == len(rows[0]) == 29                     # version 3 at error level M
    assert all(len(r) == len(rows) and set(r) <= {"0", "1"} for r in rows)
    assert rows[0][:7] == "1111111" and rows[1][:7] == "1000001"      # the finder pattern, top left


def test_longer_text_makes_a_bigger_code():
    assert len(matrix("x" * 60)) > len(matrix("x"))
