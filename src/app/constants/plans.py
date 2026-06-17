class PlanTier:
    FREE = "FREE"
    BASIC = "BASIC"
    PRO = "PRO"
    MAX = "MAX"


# Plans that unlock AI-powered goal decomposition
AI_DECOMPOSITION_PLANS = {PlanTier.BASIC, PlanTier.PRO, PlanTier.MAX}

# Plans that unlock on-demand AI reviews
AI_REVIEW_PLANS = {PlanTier.MAX}

# Max active goals per plan
MAX_GOALS_BY_PLAN = {
    PlanTier.FREE: 3,
    PlanTier.BASIC: 15,
    PlanTier.PRO: 50,
    PlanTier.MAX: 200,
}

# Max AI decompositions per month per plan
AI_DECOMPOSITIONS_PER_MONTH = {
    PlanTier.FREE: 0,
    PlanTier.BASIC: 5,
    PlanTier.PRO: 20,
    PlanTier.MAX: 100,
}
