import pytest
from parawave.storage import create_storage, register_storage


class TestStorageRegistry:
    def test_create_sqlite_storage(self, tmp_path):
        storage = create_storage("sqlite", path=str(tmp_path / ".parawave"))
        assert storage is not None

    def test_create_in_memory_storage(self):
        storage = create_storage("in_memory")
        assert storage is not None

    def test_unknown_storage_raises(self):
        with pytest.raises(ValueError, match="Unknown storage"):
            create_storage("nonexistent")

    def test_register_custom_backend(self):
        class FakeStorage:
            pass
        register_storage("_test_fake", lambda **kw: FakeStorage())
        storage = create_storage("_test_fake")
        assert isinstance(storage, FakeStorage)

    def test_error_lists_available_backends(self):
        with pytest.raises(ValueError, match="sqlite"):
            create_storage("nope")
