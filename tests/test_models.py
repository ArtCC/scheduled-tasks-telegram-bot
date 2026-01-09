"""Tests for scheduled_bot.models module."""

from scheduled_bot.models import Task


class TestTask:
    """Tests for the Task dataclass."""

    def test_task_creation_minimal(self):
        """Test creating a task with minimal required fields."""
        task = Task(
            id=1,
            chat_id=12345,
            prompt="Test prompt",
            hour=8,
            minute=30,
            timezone="UTC",
        )
        assert task.id == 1
        assert task.chat_id == 12345
        assert task.prompt == "Test prompt"
        assert task.hour == 8
        assert task.minute == 30
        assert task.timezone == "UTC"
        assert task.paused is False
        assert task.interval_minutes is None
        assert task.name is None
        assert task.days_of_week is None
        assert task.is_reminder is False

    def test_task_job_id(self):
        """Test job_id property."""
        task = Task(id=42, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.job_id == "task-42"

    def test_task_job_id_none(self):
        """Test job_id when id is None."""
        task = Task(id=None, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.job_id == ""

    def test_task_is_interval_true(self):
        """Test is_interval property when interval_minutes is set."""
        task = Task(
            id=1,
            chat_id=1,
            prompt="",
            hour=0,
            minute=0,
            timezone="UTC",
            interval_minutes=120,
        )
        assert task.is_interval is True

    def test_task_is_interval_false(self):
        """Test is_interval property when interval_minutes is None."""
        task = Task(id=1, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.is_interval is False

    def test_task_display_name_with_name(self):
        """Test display_name when name is set."""
        task = Task(
            id=1,
            chat_id=1,
            prompt="",
            hour=0,
            minute=0,
            timezone="UTC",
            name="MyTask",
        )
        assert task.display_name == "MyTask"

    def test_task_display_name_without_name(self):
        """Test display_name when name is not set."""
        task = Task(id=5, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.display_name == "Task #5"

    def test_task_display_name_no_id(self):
        """Test display_name when neither name nor id is set."""
        task = Task(id=None, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.display_name == "Task"

    def test_task_with_days_of_week(self):
        """Test task with days_of_week set."""
        task = Task(
            id=1,
            chat_id=1,
            prompt="Weekly task",
            hour=9,
            minute=0,
            timezone="UTC",
            days_of_week="mon,wed,fri",
        )
        assert task.days_of_week == "mon,wed,fri"

    def test_task_with_all_fields(self):
        """Test task with all optional fields set."""
        from datetime import datetime

        run_at = datetime(2026, 12, 31, 23, 59)
        task = Task(
            id=1,
            chat_id=12345,
            prompt="Full task",
            hour=23,
            minute=59,
            timezone="Europe/Madrid",
            run_at=run_at,
            paused=True,
            interval_minutes=60,
            name="FullTask",
            days_of_week="sat,sun",
        )
        assert task.run_at == run_at
        assert task.paused is True
        assert task.interval_minutes == 60
        assert task.name == "FullTask"
        assert task.days_of_week == "sat,sun"

    def test_task_is_reminder_default(self):
        """Test is_reminder defaults to False."""
        task = Task(id=1, chat_id=1, prompt="", hour=0, minute=0, timezone="UTC")
        assert task.is_reminder is False

    def test_task_is_reminder_true(self):
        """Test task with is_reminder set to True."""
        task = Task(
            id=1,
            chat_id=1,
            prompt="Buy milk",
            hour=10,
            minute=0,
            timezone="UTC",
            is_reminder=True,
        )
        assert task.is_reminder is True

    def test_reminder_display_name(self):
        """Test display_name for reminders without custom name."""
        task = Task(
            id=3,
            chat_id=1,
            prompt="Call mom",
            hour=18,
            minute=0,
            timezone="UTC",
            is_reminder=True,
        )
        assert task.display_name == "Reminder #3"

    def test_reminder_display_name_with_custom_name(self):
        """Test display_name for reminders with custom name."""
        task = Task(
            id=3,
            chat_id=1,
            prompt="Call mom",
            hour=18,
            minute=0,
            timezone="UTC",
            is_reminder=True,
            name="MomCall",
        )
        assert task.display_name == "MomCall"
