"""Tests for scheduled_bot.storage module."""

import os
import tempfile
from datetime import datetime

import pytest

from scheduled_bot.models import Task
from scheduled_bot.storage import TaskStorage


@pytest.fixture
def storage():
    """Create a temporary storage instance for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield TaskStorage(db_path)
    os.unlink(db_path)


@pytest.fixture
def sample_task():
    """Create a sample task for testing."""
    return Task(
        id=None,
        chat_id=12345,
        prompt="Test prompt",
        hour=8,
        minute=30,
        timezone="UTC",
    )


class TestTaskStorage:
    """Tests for TaskStorage class."""

    def test_add_task(self, storage, sample_task):
        """Test adding a task."""
        task = storage.add_task(sample_task)
        assert task.id is not None
        assert task.id > 0
        assert task.prompt == "Test prompt"

    def test_add_task_with_all_fields(self, storage):
        """Test adding a task with all optional fields."""
        task = Task(
            id=None,
            chat_id=12345,
            prompt="Full task",
            hour=9,
            minute=0,
            timezone="Europe/Madrid",
            run_at=datetime(2026, 12, 31, 23, 59),
            paused=True,
            interval_minutes=120,
            name="MyTask",
            days_of_week="mon,wed,fri",
        )
        saved = storage.add_task(task)
        assert saved.id is not None
        assert saved.name == "MyTask"
        assert saved.days_of_week == "mon,wed,fri"
        assert saved.interval_minutes == 120
        assert saved.paused is True

    def test_get_task(self, storage, sample_task):
        """Test getting a task by ID."""
        saved = storage.add_task(sample_task)
        retrieved = storage.get_task(saved.id, sample_task.chat_id)
        assert retrieved is not None
        assert retrieved.id == saved.id
        assert retrieved.prompt == "Test prompt"

    def test_get_task_not_found(self, storage):
        """Test getting a non-existent task."""
        result = storage.get_task(999, 12345)
        assert result is None

    def test_get_task_wrong_chat_id(self, storage, sample_task):
        """Test that tasks are isolated by chat_id."""
        saved = storage.add_task(sample_task)
        result = storage.get_task(saved.id, 99999)  # Different chat_id
        assert result is None

    def test_list_tasks(self, storage):
        """Test listing tasks for a chat."""
        chat_id = 12345
        for i in range(3):
            task = Task(
                id=None,
                chat_id=chat_id,
                prompt=f"Task {i}",
                hour=8 + i,
                minute=0,
                timezone="UTC",
            )
            storage.add_task(task)

        tasks = storage.list_tasks(chat_id)
        assert len(tasks) == 3
        assert [t.prompt for t in tasks] == ["Task 0", "Task 1", "Task 2"]

    def test_list_tasks_empty(self, storage):
        """Test listing tasks when none exist."""
        tasks = storage.list_tasks(12345)
        assert tasks == []

    def test_list_tasks_isolated_by_chat(self, storage):
        """Test that list only returns tasks for the specified chat."""
        storage.add_task(
            Task(id=None, chat_id=111, prompt="Chat 1", hour=8, minute=0, timezone="UTC")
        )
        storage.add_task(
            Task(id=None, chat_id=222, prompt="Chat 2", hour=9, minute=0, timezone="UTC")
        )

        tasks = storage.list_tasks(111)
        assert len(tasks) == 1
        assert tasks[0].prompt == "Chat 1"

    def test_delete_task(self, storage, sample_task):
        """Test deleting a task."""
        saved = storage.add_task(sample_task)
        result = storage.delete_task(saved.id, sample_task.chat_id)
        assert result is True
        assert storage.get_task(saved.id, sample_task.chat_id) is None

    def test_delete_task_not_found(self, storage):
        """Test deleting non-existent task returns False."""
        result = storage.delete_task(999, 12345)
        assert result is False

    def test_delete_task_wrong_chat_id(self, storage, sample_task):
        """Test that delete is isolated by chat_id."""
        saved = storage.add_task(sample_task)
        result = storage.delete_task(saved.id, 99999)  # Different chat_id
        assert result is False
        # Task should still exist
        assert storage.get_task(saved.id, sample_task.chat_id) is not None

    def test_set_paused(self, storage, sample_task):
        """Test pausing a task."""
        saved = storage.add_task(sample_task)
        assert saved.paused is False

        result = storage.set_paused(saved.id, sample_task.chat_id, True)
        assert result is True

        retrieved = storage.get_task(saved.id, sample_task.chat_id)
        assert retrieved.paused is True

    def test_set_paused_resume(self, storage):
        """Test resuming a paused task."""
        task = Task(
            id=None,
            chat_id=12345,
            prompt="Paused task",
            hour=8,
            minute=0,
            timezone="UTC",
            paused=True,
        )
        saved = storage.add_task(task)

        result = storage.set_paused(saved.id, task.chat_id, False)
        assert result is True

        retrieved = storage.get_task(saved.id, task.chat_id)
        assert retrieved.paused is False

    def test_set_paused_not_found(self, storage):
        """Test pausing non-existent task returns False."""
        result = storage.set_paused(999, 12345, True)
        assert result is False

    def test_update_prompt(self, storage, sample_task):
        """Test updating a task's prompt."""
        saved = storage.add_task(sample_task)
        result = storage.update_prompt(saved.id, sample_task.chat_id, "New prompt")
        assert result is True

        retrieved = storage.get_task(saved.id, sample_task.chat_id)
        assert retrieved.prompt == "New prompt"

    def test_update_prompt_not_found(self, storage):
        """Test updating non-existent task returns False."""
        result = storage.update_prompt(999, 12345, "New prompt")
        assert result is False

    def test_load_all(self, storage):
        """Test loading all tasks across all chats."""
        storage.add_task(
            Task(id=None, chat_id=111, prompt="Task 1", hour=8, minute=0, timezone="UTC")
        )
        storage.add_task(
            Task(id=None, chat_id=222, prompt="Task 2", hour=9, minute=0, timezone="UTC")
        )

        all_tasks = list(storage.load_all())
        assert len(all_tasks) == 2

    def test_task_with_run_at_persisted(self, storage):
        """Test that run_at datetime is correctly persisted."""
        run_at = datetime(2026, 6, 15, 10, 30)
        task = Task(
            id=None,
            chat_id=12345,
            prompt="One-time task",
            hour=10,
            minute=30,
            timezone="UTC",
            run_at=run_at,
        )
        saved = storage.add_task(task)
        retrieved = storage.get_task(saved.id, task.chat_id)

        assert retrieved.run_at is not None
        assert retrieved.run_at.year == 2026
        assert retrieved.run_at.month == 6
        assert retrieved.run_at.day == 15
