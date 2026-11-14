from src.scene_planner import (
    ScenePlanner,
    ScenePlannerError,
)


prompt = """
Create a funny 60-second vertical video about a
French man doing his weekly grocery shopping.

At first he thinks he will spend very little money,
but each aisle surprises him with higher prices.

He reacts humorously and speaks French.

The video should look realistic and cinematic,
with one consistent main character throughout.
"""


planner = ScenePlanner()


try:

    plan = planner.create_plan(
        user_prompt=prompt,
        target_duration=60,
    )

    print()
    print("TITLE:")
    print(plan.title)

    print()
    print("CHARACTER:")
    print(plan.character_description)

    print()
    print("STYLE:")
    print(plan.style_description)

    print()
    print(
        "TOTAL DURATION:",
        plan.total_duration,
        "seconds",
    )

    print()

    for scene in plan.scenes:

        print(
            "=" * 60
        )

        print(
            f"SCENE {scene.number}"
        )

        print(
            "Duration:",
            scene.duration,
        )

        print()
        print("Visual:")
        print(
            scene.visual_prompt
        )

        print()
        print("Dialogue:")
        print(
            scene.dialogue
            or "[No dialogue]"
        )

        print()

except ScenePlannerError as exc:

    print(
        "Scene planner error:",
        exc,
    )