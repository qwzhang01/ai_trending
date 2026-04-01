"""crew/quality_review — 质量审核 Crew 包.

对外只暴露 QualityReviewCrew，由 quality_review_node 调用。

使用示例::

    from ai_trending.crew.quality_review import QualityReviewCrew

    review_result, token_usage = QualityReviewCrew().run(
        report_content=...,
        scoring_result=...,
        current_date=...,
    )
"""

from ai_trending.crew.quality_review.crew import QualityReviewCrew

__all__ = ["QualityReviewCrew"]
