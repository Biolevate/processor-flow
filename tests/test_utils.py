from forge.activity import get_meta_index


def test_get_meta_index():
    class MockMeta:
        def __init__(self, meta):
            self.meta = meta

    metas = [MockMeta("meta1"), MockMeta("meta2"), MockMeta("meta3")]

    assert get_meta_index("meta1", metas) == 0
    assert get_meta_index("meta2", metas) == 1
    assert get_meta_index("meta3", metas) == 2
    assert get_meta_index("meta4", metas) == -1
