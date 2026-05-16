"""Statistical analysis of character performance."""

import pandas as pd


def compute_statistics(df):
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
    score_cols = [c for c in df.columns if c != "timestamp"]
    return df[score_cols].rank(axis=1, ascending=False, method="average").mean()


def consistency_adjusted_score(stats_df, k=0.5):
    return stats_df["mean"] - k * stats_df["std"].fillna(0)


def full_analysis(df, k=0.5):
    if df.empty:
        return pd.DataFrame()
    stats = compute_statistics(df)
    stats["avg_rank"] = average_rank(df)
    stats["adjusted"] = consistency_adjusted_score(stats, k)
    stats = stats.sort_values("adjusted", ascending=False)
    return stats
