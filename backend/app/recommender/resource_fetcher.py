"""
Resource Fetcher: Data access layer for the recommendation system.

Fetches candidate learning resources from the catalog and user interaction
history from Supabase. Performs pre-filtering by topic and resource type
before passing candidates to the scoring engine.
"""

import pandas as pd
from supabase import Client


def fetch_candidate_resources(
    supabase: Client,
    topic_ids: list[str],
    resource_types: list[str] | None = None,
) -> pd.DataFrame:
    """
    Fetch all learning resources matching the given topic IDs.

    Joins learning_resources with resource_topics to get per-topic rows.
    Optionally filters by resource_type.

    Args:
        supabase: Supabase client for database access.
        topic_ids: List of topic UUIDs to fetch resources for.
        resource_types: Optional filter for resource types
                        (e.g., ['article', 'video']).

    Returns:
        DataFrame with columns:
            resource_id, title, description, resource_type, url,
            difficulty_level, estimated_minutes, quality_score,
            metadata, topic_id
        Empty DataFrame if no resources found.
    """
    if not topic_ids:
        return pd.DataFrame()

    # Fetch resource-topic links for the given topics
    rt_res = (
        supabase.table("resource_topics")
        .select("resource_id, topic_id")
        .in_("topic_id", topic_ids)
        .execute()
    )
    if not rt_res.data:
        return pd.DataFrame()

    rt_df = pd.DataFrame(rt_res.data)
    resource_ids = rt_df["resource_id"].unique().tolist()

    # Fetch the actual resources
    query = (
        supabase.table("learning_resources")
        .select("id, title, description, resource_type, url, difficulty_level, "
                "estimated_minutes, quality_score, metadata")
        .in_("id", resource_ids)
    )

    if resource_types:
        query = query.in_("resource_type", resource_types)

    resources_res = query.execute()
    if not resources_res.data:
        return pd.DataFrame()

    resources_df = pd.DataFrame(resources_res.data)
    resources_df.rename(columns={"id": "resource_id"}, inplace=True)

    # Join with resource_topics to get per-topic rows
    # A resource tagged to multiple topics will appear multiple times
    merged = resources_df.merge(rt_df, on="resource_id", how="inner")

    # Filter to only requested topics (in case of stale data)
    merged = merged[merged["topic_id"].isin(topic_ids)]

    return merged


def fetch_user_interactions(
    supabase: Client,
    user_id: str,
) -> pd.DataFrame:
    """
    Fetch all past resource interactions for a user.

    Used for:
    - Freshness scoring (time since last interaction per topic)
    - Diversity scoring (distribution of resource types consumed)
    - De-duplication (excluding completed resources)

    Args:
        supabase: Supabase client for database access.
        user_id: The student's user ID.

    Returns:
        DataFrame with columns:
            resource_id, interaction_type, rating, interacted_at
        Empty DataFrame if no interactions found.
    """
    res = (
        supabase.table("user_resource_interactions")
        .select("resource_id, interaction_type, rating, interacted_at")
        .eq("user_id", user_id)
        .order("interacted_at", desc=True)
        .execute()
    )

    if not res.data:
        return pd.DataFrame(columns=[
            "resource_id", "interaction_type", "rating", "interacted_at"
        ])

    df = pd.DataFrame(res.data)
    df["interacted_at"] = pd.to_datetime(df["interacted_at"], utc=True)
    return df


def fetch_resource_topic_names(
    supabase: Client,
    topic_ids: list[str],
) -> dict[str, str]:
    """
    Fetch topic names for a list of topic IDs.

    Args:
        supabase: Supabase client for database access.
        topic_ids: List of topic UUIDs.

    Returns:
        Dict mapping topic_id → topic_name.
    """
    if not topic_ids:
        return {}

    res = (
        supabase.table("topics")
        .select("id, name")
        .in_("id", topic_ids)
        .execute()
    )

    if not res.data:
        return {}

    return {t["id"]: t["name"] for t in res.data}
