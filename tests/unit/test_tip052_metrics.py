from __future__ import annotations

from vibemql5.parsers.report import parse_report


def test_balance_and_equity_drawdown_are_distinct(tmp_path):
    report = tmp_path / "report.htm"
    report.write_text(
        """
        <table>
          <tr><td>Balance Drawdown Maximal:</td><td>5.41 (0.05%)</td></tr>
          <tr><td>Equity Drawdown Maximal:</td><td>6.38 (0.06%)</td></tr>
          <tr><td>Total Net Profit:</td><td>-4.89</td></tr>
        </table>
        """,
        encoding="utf-8",
    )
    out = parse_report(report)
    assert out["status"] == "PARSED"
    assert out["metrics"]["max_drawdown_pct"] == 0.05
    assert out["metrics"]["balance_drawdown_max_pct"] == 0.05
    assert out["metrics"]["equity_drawdown_max_pct"] == 0.06
    assert out["metrics"]["net_profit"] == -4.89
