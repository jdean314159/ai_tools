from agent_lib import (
    ExternalSessionCoordinator,
    InMemoryMailbox,
)
from agent_lib.examples import (
    make_external_programming_team,
    make_external_session_coordinator,
)


def test_external_team_registration_and_mailbox_flow() -> None:
    team = make_external_programming_team(
        project_id="demo",
        mentor_id="mentor",
        worker_ids=("worker-a", "worker-b"),
        critic_id="critic",
        scout_ids=("scout",),
    )
    coordinator = make_external_session_coordinator(team)

    message = coordinator.send(
        "mentor",
        "worker-a",
        kind="finding",
        subject="Inspect parser",
        body="Check parser.py and summarize likely breakpoints.",
        thread_id="task-1",
    )

    inbox = coordinator.inbox("worker-a", thread_id="task-1")
    assert len(inbox) == 1
    assert inbox[0].message_id == message.message_id
    assert inbox[0].subject == "Inspect parser"


def test_external_session_reservations_are_advisory() -> None:
    coordinator = ExternalSessionCoordinator(InMemoryMailbox())
    team = make_external_programming_team(project_id="demo", worker_ids=("worker-a", "worker-b"))
    coordinator.register_team(team)

    first = coordinator.reserve_paths(
        "worker-a", ["src/parser.py"], thread_id="task-1", note="Investigating bug"
    )
    second = coordinator.reserve_paths("worker-b", ["src/parser.py"], thread_id="task-1")

    assert first[0].status == "active"
    assert second[0].status == "conflict"
    assert second[0].metadata["current_holder"] == "worker-a"

    released = coordinator.release_paths("worker-a", ["src/parser.py"])
    assert released[0].status == "released"
