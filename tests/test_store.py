from sonos_sleep_bgm.models import Schedule, Source
from sonos_sleep_bgm.store import Store


def make_schedule(name="夜BGM", time="21:00"):
    return Schedule(name=name, time=time, source=Source(type="playlist", title="Sleep"))


def test_add_and_list(tmp_path):
    store = Store(tmp_path / "data.json")
    created = store.add_schedule(make_schedule())
    assert created.id
    assert len(store.list_schedules()) == 1


def test_persists_across_instances(tmp_path):
    path = tmp_path / "data.json"
    s1 = Store(path)
    created = s1.add_schedule(make_schedule(name="セットA"))
    s1.update_settings(room="主書斎")

    s2 = Store(path)  # 再読み込み
    assert s2.get_settings().room == "主書斎"
    got = s2.get_schedule(created.id)
    assert got is not None and got.name == "セットA"


def test_update_schedule(tmp_path):
    store = Store(tmp_path / "data.json")
    created = store.add_schedule(make_schedule())
    updated = store.update_schedule(created.id, make_schedule(name="更新後", time="07:00"))
    assert updated.id == created.id
    assert store.get_schedule(created.id).name == "更新後"


def test_delete_schedule(tmp_path):
    store = Store(tmp_path / "data.json")
    created = store.add_schedule(make_schedule())
    assert store.delete_schedule(created.id) is True
    assert store.delete_schedule(created.id) is False
    assert store.list_schedules() == []


def test_multiple_sets_stocked(tmp_path):
    store = Store(tmp_path / "data.json")
    store.add_schedule(make_schedule(name="夜", time="21:00"))
    store.add_schedule(make_schedule(name="朝", time="09:00"))
    names = {s.name for s in store.list_schedules()}
    assert names == {"夜", "朝"}
