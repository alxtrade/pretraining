import asyncio
import unittest
from model.data import Model, ModelId, ModelMetadata
from model.model_tracker import ModelTracker

from model.model_updater import ModelUpdater
from model.storage.disk.disk_model_store import DiskModelStore
from tests.model.storage.fake_model_metadata_store import FakeModelMetadataStore
from tests.model.storage.fake_remote_model_store import FakeRemoteModelStore
from transformers import DistilBertModel, DistilBertConfig


class TestModelUpdater(unittest.TestCase):
    def setUp(self):
        self.model_tracker = ModelTracker()
        self.local_store = DiskModelStore("test-models")
        self.remote_store = FakeRemoteModelStore()
        self.metadata_store = FakeModelMetadataStore()
        self.model_updater = ModelUpdater(
            metadata_store=self.metadata_store,
            remote_store=self.remote_store,
            local_store=self.local_store,
            model_tracker=self.model_tracker,
        )

    def tearDown(self):
        self.local_store.delete_unreferenced_models(dict(), 0)

    def test_get_metadata(self):
        hotkey = "test_hotkey"
        model_id = ModelId(
            namespace="test_model",
            name="test_name",
            hash="test_hash",
            commit="test_commit",
        )
        asyncio.run(self.metadata_store.store_model_metadata(hotkey, model_id))

        metadata = asyncio.run(self.model_updater._get_metadata(hotkey))

        self.assertEqual(metadata.id, model_id)
        self.assertIsNotNone(metadata.block)

    def test_sync_model_bad_metadata(self):
        hotkey = "test_hotkey"
        model_id = ModelId(
            namespace="test_model",
            name="test_name",
            hash="test_hash",
            commit="bad_commit",
        )

        # Setup the metadata with a commit that doesn't exist in the remote store.
        asyncio.run(self.metadata_store.store_model_metadata(hotkey, model_id))

        # FakeRemoteModelStore raises a KeyError but HuggingFace may raise other exceptions.
        with self.assertRaises(Exception):
            asyncio.run(self.model_updater.sync_model(hotkey))

    def test_sync_model_same_metadata(self):
        hotkey = "test_hotkey"
        model_id = ModelId(
            namespace="test_model",
            name="test_name",
            hash="test_hash",
            commit="test_commit",
        )
        model_metadata = ModelMetadata(id=model_id, block=1)

        pt_model = DistilBertModel(
            config=DistilBertConfig(
                vocab_size=256, n_layers=2, n_heads=4, dim=100, hidden_dim=400
            )
        )
        model = Model(id=model_id, pt_model=pt_model)

        # Setup the metadata, local, and model_tracker to match.
        asyncio.run(self.metadata_store.store_model_metadata(hotkey, model_id))
        self.local_store.store_model(hotkey, model)

        self.model_tracker.on_miner_model_updated(hotkey, model_metadata)

        asyncio.run(self.model_updater.sync_model(hotkey))

        # Tracker information did not change.
        self.assertEqual(
            self.model_tracker.get_model_metadata_for_miner_hotkey(hotkey),
            model_metadata,
        )

    def test_sync_model_new_metadata(self):
        hotkey = "test_hotkey"
        model_id = ModelId(
            namespace="test_model",
            name="test_name",
            hash="test_hash",
            commit="test_commit",
        )
        model_metadata = ModelMetadata(id=model_id, block=1)

        pt_model = DistilBertModel(
            config=DistilBertConfig(
                vocab_size=256, n_layers=2, n_heads=4, dim=100, hidden_dim=400
            )
        )
        model = Model(id=model_id, pt_model=pt_model)

        # Setup the metadata and remote store but not local or the model_tracker.
        asyncio.run(self.metadata_store.store_model_metadata(hotkey, model_id))
        asyncio.run(self.remote_store.upload_model(model))

        self.assertIsNone(
            self.model_tracker.get_model_metadata_for_miner_hotkey(hotkey)
        )

        # Our local store raises an exception from the Transformers.from_pretrained method if not found.
        with self.assertRaises(Exception):
            self.local_store.retrieve_model(hotkey, model_id)

        asyncio.run(self.model_updater.sync_model(hotkey))

        self.assertEqual(
            self.model_tracker.get_model_metadata_for_miner_hotkey(hotkey),
            model_metadata,
        )
        self.assertEqual(
            str(self.local_store.retrieve_model(hotkey, model_id)), str(model)
        )