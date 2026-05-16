"""Statistical analysis of character performance."""

import pandas as pd
import numpy as np


def compute_statistics(df):
    """Compute per-character statistics from match data."""
    score_cols = [c for c in df.columns if c != "timestamp"]
    stats = []
    for col in score_cols:
        s = df[col].dropna()
        if len(s) > 0:
            stats.append(
                {
                    "character": col,
                    "mean": s.mean(),
                    "median": s.median(),
                    "std": s.std(),
                    "min": s.min(),
                    "max": s.max(),
                    "p75": s.quantile(0.75),
                    "matches": len(s),
                }
            )
    return pd.DataFrame(stats).set_index("character")


def average_rank(df):
    """Compute average rank per character across all matches."""
    score_cols = [c for c in df.columns if c != "timestamp"]
    return df[score_cols].rank(axis=1, ascending=False, method="average").mean()


def consistency_adjusted_score(stats_df, k=0.5):
    """adjusted = mean - k * std. Higher is better."""
    return stats_df["mean"] - k * stats_df["std"].fillna(0)


def contribution_pct(df, stats_df):
    """Each character's avg score as % of avg total match score."""
    score_cols = [c for c in df.columns if c != "timestamp"]
    avg_total = df[score_cols].sum(axis=1).mean()
    return (stats_df["mean"] / avg_total * 100).round(1)


def coefficient_of_variation(stats_df):
    """std / mean. Lower = more consistent."""
    cv = (stats_df["std"] / stats_df["mean"] * 100).fillna(0).round(1)
    return cv


def assign_tier(stats_df):
    """Assign S/A/B/C/D tiers based on adjusted score percentiles."""
    adjusted = stats_df["adjusted"]
    p25 = adjusted.quantile(0.25)
    p50 = adjusted.quantile(0.50)
    p75 = adjusted.quantile(0.75)

    def tier(val):
        if val >= p75:
            return "S"
        elif val >= p50:
            return "A"
        elif val >= p25:
            return "B"
        else:
            return "C"

    return adjusted.apply(tier)


def replace_priority(stats_df, df):
    """Composite score for replacement priority. Higher = worse character.

    Combines:
    - Low contribution % (bad)
    - High CV (inconsistent)
    - Low adjusted score (bad)
    """
    contrib = contribution_pct(df, stats_df)
    cv = coefficient_of_variation(stats_df)
    adjusted = stats_df["adjusted"]

    # Normalize each factor to 0-100 scale (higher = worse)
    contrib_score = 100 - (contrib - contrib.min()) / (contrib.max() - contrib.min() + 1e-9) * 100
    cv_score = (cv - cv.min()) / (cv.max() - cv.min() + 1e-9) * 100
    adj_score = 100 - (adjusted - adjusted.min()) / (adjusted.max() - adjusted.min() + 1e-9) * 100

    # Weighted composite
    priority = 0.3 * contrib_score + 0.3 * cv_score + 0.4 * adj_score
    return priority.round(1)


def team_trend(df, window=5):
    """Compute rolling average of total match scores."""
    score_cols = [c for c in df.columns if c != "timestamp"]
    totals = df[score_cols].sum(axis=1)
    rolling = totals.rolling(window=window, min_periods=1).mean()
    return rolling


def full_analysis(df, k=0.5):
    """Run full analysis and return combined results."""
    if df.empty:
        return pd.DataFrame()

    stats = compute_statistics(df)
    stats["avg_rank"] = average_rank(df)
    stats["adjusted"] = consistency_adjusted_score(stats, k)
    stats["contribution_%"] = contribution_pct(df, stats)
    stats["cv"] = coefficient_of_variation(stats)
    stats["tier"] = assign_tier(stats)
    stats["replace_priority"] = replace_priority(stats, df)
    stats = stats.sort_values("adjusted", ascending=False)
    return stats


def format_report(df, k=0.5):
    """Generate a human-readable analysis report."""
    if df.empty:
        return "No match data found."

    results = full_analysis(df, k)
    lines = []

    lines.append("=" * 70)
    lines.append(f"CHARACTER PERFORMANCE REPORT ({len(df)} matches)")
    lines.append("=" * 70)
    lines.append("")

    # Team summary
    score_cols = [c for c in df.columns if c != "timestamp"]
    totals = df[score_cols].sum(axis=1)
    lines.append(f"Team avg total: {totals.mean():,.0f}  |  Best match: {totals.max():,.0f}  |  Worst: {totals.min():,.0f}")

    trend = team_trend(df, window=5)
    if len(trend) >= 2:
        diff = trend.iloc[-1] - trend.iloc[0]
        if diff > 0:
            direction = "[UP]"
        elif diff < 0:
            direction = "[DOWN]"
        else:
            direction = "[FLAT]"
        lines.append(f"Team trend (last {min(5, len(df))} matches): {direction} {diff:+,.0f}")
    lines.append("")

    # Tier summary
    tiers = results.groupby("tier").size()
    tier_str = ", ".join(f"{t}: {c}" for t, c in tiers.items())
    lines.append(f"Tiers: {tier_str}")
    lines.append("")

    # Top performers
    lines.append("--- Top Performers (keep these) ---")
    top = results.head(5)
    for name, row in top.iterrows():
        lines.append(
            f"  {name:20s}  {row['mean']:>8,.0f} avg  |  {row['tier']}  |  {row['contribution_%']:5.1f}% of total  |  CV: {row['cv']:.1f}%"
        )
    lines.append("")

    # Replace candidates
    lines.append("--- Replace Candidates (consider swapping) ---")
    worst = results.tail(5).sort_values("replace_priority", ascending=False)
    for name, row in worst.iterrows():
        warn = " [HIGH VAR]" if row["cv"] > 15 else ""
        lines.append(
            f"  {name:20s}  {row['mean']:>8,.0f} avg  |  {row['tier']}  |  {row['contribution_%']:5.1f}% of total  |  CV: {row['cv']:.1f}%{warn}"
        )
    lines.append("")

    # Full table
    lines.append("--- Full Statistics ---")
    col_order = ["adjusted", "avg_rank", "mean", "median", "std", "p75", "min", "max", "contribution_%", "cv", "tier", "replace_priority", "matches"]
    available = [c for c in col_order if c in results.columns]
    lines.append(results[available].to_string())
    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)
