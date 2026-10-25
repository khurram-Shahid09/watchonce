import pytest

from config.celery import app


@pytest.mark.parametrize(
    ("task_name", "queue"),
    [
        ("engine.compiler.tasks.compile_recording", "compile"),
        ("engine.runner.tasks.execute_run", "run"),
        ("engine.healer.tasks.repair_step", "heal"),
    ],
)
def test_tasks_route_to_their_own_queue(task_name: str, queue: str) -> None:
    route = app.amqp.router.route({}, task_name)
    assert route["queue"].name == queue
    assert route["queue"].exchange.name == queue
    assert route["queue"].routing_key == queue


def test_queues_do_not_share_bindings() -> None:
    keys = {(q.exchange.name, q.routing_key) for q in app.conf.task_queues}
    assert len(keys) == 3
