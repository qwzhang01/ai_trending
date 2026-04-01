"""crew/editorial_planning — 编辑部选题规划 Crew 包.

对外只暴露 EditorialPlanningCrew，由 editorial_planning_node 调用。

使用示例::

    from ai_trending.crew.editorial_planning import EditorialPlanningCrew

    plan = EditorialPlanningCrew().run(scoring_result=..., current_date=...)
"""

from ai_trending.crew.editorial_planning.crew import EditorialPlanningCrew

__all__ = ["EditorialPlanningCrew"]
