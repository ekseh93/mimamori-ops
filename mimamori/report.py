import math
from datetime import datetime, timezone


def iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat().replace("+00:00", "Z")


def render_report(target_id, samples, start, end, simulated=False):
    if end <= start or start % 300 or end % 300:
        raise ValueError("report period must be increasing and aligned to 5-minute UTC boundaries")
    samples = sorted({row["slot"]: row for row in samples
                      if start <= row["slot"] < end and row["target_id"] == target_id}.values(),
                     key=lambda row: row["slot"])
    expected = (end - start) // 300
    count = len(samples)
    good = sum(row["ok"] for row in samples)
    ratio = f"{good / count * 100:.2f}%" if count else "算出不可（観測なし）"
    latencies = sorted(row["latency_ms"] for row in samples if row["ok"])
    p95 = f"{latencies[math.ceil(len(latencies) * .95) - 1]} ms" if latencies else "算出不可"
    lines = ["# みまもり運用レポート", "",
             "**模擬訓練データ / 実サービスの稼働実績ではありません。**" if simulated
             else "実測サンプルの集計。継続稼働や原因の確定を意味しません。", "",
             f"対象ID: `{target_id}`", f"期間: {iso(start)} 以上 / {iso(end)} 未満（UTC）", "",
             "| 項目 | 結果 |", "|---|---|",
             f"| 観測数 / 予定数 | {count} / {expected} |",
             f"| 観測カバー率 | {count / expected * 100:.2f}% |",
             f"| 未観測枠 | {max(0, expected - count)} |",
             f"| 観測成功率 | {ratio} |", f"| 成功応答の標本p95 | {p95} |", "",
             "観測成功率は月間稼働率・SLAではありません。5分間の間に発生した障害は検出できない場合があります。",
             "未観測の枠を成功として補完していません。p95は成功した少数標本の応答時間です。", "",
             "## 観測履歴（最新100件）", "",
             "予定枠と実際の確認開始時刻を分けて記載しています。通知は遅延する場合があります。", "",
             "| 予定枠 UTC | 確認開始 UTC | 判定 | 理由 | HTTP | TLS残日数 |",
             "|---|---|---|---|---|---|"]
    for row in samples[-100:]:
        observed = iso(row["observed_at"]) if row.get("observed_at") is not None else "未記録/模擬"
        lines.append(f"| {iso(row['slot'])} | {observed} | {'成功' if row['ok'] else '失敗'} | "
                     f"{row['reason']} | {row['status'] if row['status'] is not None else '-'} | "
                     f"{row['tls_days'] if row['tls_days'] is not None else '-'} |")
    if not count:
        lines.append("| - | - | 未観測 | 監視設定と収集処理を確認 | - | - |")
    if count > 100:
        lines.append(f"\n古い{count - 100}件は表から省略。集計値には期間内の全観測を含めています。")
    lines += ["", "## 担当者への引継ぎ", "",
              "- 影響範囲: このURLの観測結果のみ。顧客影響・他機能への影響は未確認。",
              "- 一次確認: DNS → TLS → HTTP → 直近の変更 → 監視側のエラーを確認。",
              "- 原因: 未確定。応答コードだけでサーバー・ネットワーク・担当者の責任を断定しない。",
              "- TLS残日数が14日以下の場合は更新予定を確認（期限予告の自動通知は未実装）。",
              "- 担当者・実施した対応・再発防止: レビュー時に記入。", ""]
    return "\n".join(lines)
