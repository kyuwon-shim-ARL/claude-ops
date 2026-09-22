"""Uploads land inside the project, or they do not land at all.

The endpoint is a write primitive reachable with one shared secret, so most of
what is tested here is refusal: a tmux lookup that failed, a session parked
outside the projects root, a `.ctb-uploads` that someone replaced with a
symlink, a body bigger than it claimed to be. The happy path is one test; the
ways out of the project are the rest.
"""

import asyncio
import os
import pytest
from fastapi.testclient import TestClient

import ctb_dashboard.server as _srv
import ctb_dashboard.session_upload as _up
from ctb_dashboard.server import app

_SECRET = "upload-secret-under-test"
_AUTH = {"X-CTB-Secret": _SECRET}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A projects root with one project, and a session sitting in a subdir."""
    root = tmp_path / "projects"
    pane = root / "demo" / "src"
    pane.mkdir(parents=True)
    monkeypatch.setenv("CTB_PROJECTS_ROOT", str(root))
    monkeypatch.setattr(_srv, "_CONTROL_SECRET", _SECRET)
    monkeypatch.setattr(_srv, "session_exists", lambda name: True)
    monkeypatch.setattr(_srv, "get_session_path", lambda name: str(pane))
    _srv._upload_limiter.reset()
    return root / "demo"


@pytest.fixture
def client(project):
    return TestClient(app)


def _post(client, body, name="a.txt", session="demo"):
    return client.post(
        f"/api/sessions/{session}/upload?filename={name}",
        content=body,
        headers=_AUTH,
    )


def test_upload_lands_in_project_root_not_the_pane_cwd(client, project):
    r = _post(client, b"hello")
    assert r.status_code == 200, r.text
    body = r.json()
    # The session's cwd was demo/src; the file belongs at the project root, the
    # one place the user can name without knowing where the pane wandered to.
    assert body["path"] == str(project / ".ctb-uploads" / "a.txt")
    assert (project / ".ctb-uploads" / "a.txt").read_bytes() == b"hello"
    assert body["bytes"] == 5


def test_upload_directory_ignores_itself(client, project):
    _post(client, b"x")
    assert (project / ".ctb-uploads" / ".gitignore").read_text() == "*\n"


def test_same_name_twice_does_not_overwrite(client, project):
    first = _post(client, b"one").json()["name"]
    second = _post(client, b"two").json()["name"]
    assert first == "a.txt" and second == "a-2.txt"
    assert (project / ".ctb-uploads" / "a.txt").read_bytes() == b"one"


def test_traversal_in_filename_cannot_leave_the_directory(client, project):
    r = _post(client, b"x", name="..%2F..%2Fescaped.txt")
    assert r.status_code == 200
    assert not (project.parent / "escaped.txt").exists()
    stored = r.json()["name"]
    assert "/" not in stored and stored not in ("..", ".")


def test_unauthenticated_upload_is_refused(project):
    c = TestClient(app)
    r = c.post("/api/sessions/demo/upload?filename=a.txt", content=b"x")
    assert r.status_code == 403
    assert not (project / ".ctb-uploads").exists(), "body was accepted before auth"


def test_body_over_the_limit_leaves_no_partial_file(client, project, monkeypatch):
    monkeypatch.setattr(_srv, "_UPLOAD_MAX", 10)
    r = _post(client, b"x" * 50)
    assert r.status_code == 413
    # A truncated file would be handed to Claude as if it were whole.
    assert list((project / ".ctb-uploads").glob("a*")) == []


def test_lying_content_length_does_not_get_past_the_ceiling(client, project, monkeypatch):
    """The ceiling counts bytes received, not what the caller declared."""
    monkeypatch.setattr(_srv, "_UPLOAD_MAX", 10)
    r = client.post(
        "/api/sessions/demo/upload?filename=b.bin",
        content=iter([b"x" * 40, b"x" * 40]),      # chunked: no Content-Length
        headers=_AUTH,
    )
    assert r.status_code == 413
    assert list((project / ".ctb-uploads").glob("b*")) == []


def test_empty_body_is_refused(client, project):
    assert _post(client, b"").status_code == 400
    assert list((project / ".ctb-uploads").glob("a*")) == []


def test_symlinked_upload_dir_is_refused(client, project, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / ".ctb-uploads").symlink_to(outside)
    r = _post(client, b"x")
    assert r.status_code == 409
    assert list(outside.iterdir()) == [], "write followed a symlink out of the project"


def test_session_outside_projects_root_is_refused(client, tmp_path, monkeypatch):
    monkeypatch.setattr(_srv, "get_session_path", lambda name: str(tmp_path / "elsewhere"))
    (tmp_path / "elsewhere").mkdir()
    r = _post(client, b"x")
    assert r.status_code == 409
    assert not (tmp_path / "elsewhere" / ".ctb-uploads").exists()


def test_failed_tmux_lookup_does_not_write_to_the_server_cwd(client, monkeypatch):
    """get_session_path returns '' when tmux fails; Path('') is the cwd."""
    monkeypatch.setattr(_srv, "get_session_path", lambda name: "")
    r = _post(client, b"x")
    assert r.status_code == 409
    assert not os.path.exists(os.path.join(os.getcwd(), ".ctb-uploads"))


def test_pane_targeting_session_name_is_refused(client):
    """'demo:1.0' is a valid name by the shared regex and a tmux pane target."""
    r = _post(client, b"x", session="demo:1.0")
    assert r.status_code == 422


def test_directory_quota_refuses_when_full(client, project, monkeypatch):
    # 10, not 8: the self-ignoring .gitignore is two of the bytes the folder
    # holds, and the quota counts everything in there.
    monkeypatch.setattr(_up, "MAX_DIR_BYTES", 10)
    assert _post(client, b"12345678", name="big.bin").status_code == 200
    r = _post(client, b"more", name="next.bin")
    assert r.status_code == 507


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"),
    ("a/b/c.txt", "c.txt"),
    ("C:\\Users\\x\\note.md", "note.md"),
    ("", "upload"),
    ("...", "upload"),
    ("hello\x00.txt", "hello_.txt"),
])
def test_safe_name(raw, expected):
    assert _up.safe_name(raw) == expected


def test_safe_name_keeps_the_extension_when_truncating():
    long = "가" * 200 + ".csv"
    out = _up.safe_name(long)
    assert out.endswith(".csv")
    assert len(out.encode("utf-8")) <= 100


def test_safe_name_normalises_decomposed_hangul():
    """iOS sends NFD; the same file picked twice must be the same name."""
    import unicodedata
    nfd = unicodedata.normalize("NFD", "사진.png")
    assert _up.safe_name(nfd) == "사진.png"


# --- what the second adversarial pass found ----------------------------------

def test_a_symlinked_project_directory_cannot_redirect_the_write(tmp_path):
    """O_NOFOLLOW on the last component is not enough: swap the *project*
    directory for a symlink and every write follows it out of the root.

    Aimed at open_upload_dir directly, because that is the state a race
    produces -- the path was resolved and legitimate, and the directory was
    replaced afterwards. Going through the endpoint would prove nothing here:
    the resolve at the front refuses a symlink that is already in place, so
    the test would pass with the guarantee removed.
    """
    root = tmp_path / "projects"
    outside = tmp_path / "outside"
    (root).mkdir()
    outside.mkdir()
    (root / "demo").symlink_to(outside)

    with pytest.raises(_up.UploadError) as caught:
        _up.open_upload_dir(root, "demo")
    assert caught.value.code == "unsafe_dir"
    assert list(outside.iterdir()) == [], "the write followed a symlinked ancestor"


def test_a_symlinked_project_is_refused_through_the_endpoint_too(client, project, tmp_path):
    """A smoke check on the whole path. It does not isolate the O_NOFOLLOW
    chain -- replacing the project also removes the pane's own directory, so
    the refusal can come from the resolve at the front. The test above is the
    one that pins the chain itself."""
    outside = tmp_path / "outside"
    outside.mkdir()
    import shutil
    shutil.rmtree(project)
    (project.parent / "demo").symlink_to(outside)
    assert _post(client, b"x").status_code == 409
    assert list(outside.iterdir()) == []


def test_concurrent_uploads_cannot_both_claim_the_last_bytes(client, project, monkeypatch):
    """Two requests that each read 'there is room' would each write it."""
    monkeypatch.setattr(_up, "MAX_DIR_BYTES", 40)
    import threading
    results, lock = [], threading.Lock()

    def push(i):
        c = TestClient(app)
        r = c.post(f"/api/sessions/demo/upload?filename=f{i}.bin",
                   content=b"y" * 15, headers=_AUTH)
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=push, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    on_disk = sum(f.stat().st_size for f in (project / ".ctb-uploads").iterdir())
    assert on_disk <= 40, f"quota blown: {on_disk} bytes, {results}"
    assert 200 in results, f"every upload was refused: {results}"


def test_a_slow_body_is_cut_off_at_the_deadline(client, project, monkeypatch):
    """A caller dribbling bytes held two descriptors for as long as it liked."""
    monkeypatch.setattr(_srv, "_UPLOAD_TIMEOUT", 0.2)

    def dribble():
        import time
        for _ in range(20):
            time.sleep(0.05)
            yield b"x"

    r = client.post("/api/sessions/demo/upload?filename=slow.bin",
                    content=dribble(), headers=_AUTH)
    assert r.status_code == 408
    assert list((project / ".ctb-uploads").glob("slow*")) == []


def test_a_write_error_leaves_no_partial_file(client, project, monkeypatch):
    """ENOSPC mid-stream used to commit whatever had already landed."""
    real = _up.write_all

    def out_of_space(fd, data):
        # What ENOSPC looks like from here: some of it lands, then the write
        # fails. The bytes already on disk are the partial file.
        real(fd, data[: len(data) // 2])
        raise _up.UploadError("write_failed", 500, "no space left on device")

    monkeypatch.setattr(_srv, "_upload_write", out_of_space)
    r = client.post("/api/sessions/demo/upload?filename=partial.bin",
                    content=b"aabb", headers=_AUTH)
    assert r.status_code == 500
    assert list((project / ".ctb-uploads").glob("partial*")) == [], "a partial file survived"


def test_cleanup_does_not_delete_a_file_that_took_the_name(client, project, monkeypatch):
    """There is no unlink-by-descriptor, so cleanup by name can remove
    whatever replaced it. It must check the inode first."""
    up = project / ".ctb-uploads"
    up.mkdir()
    (up / "victim.txt").write_bytes(b"someone else's file")
    fd = os.open(up / "victim.txt", os.O_RDONLY)
    try:
        other = os.open(up / "decoy.txt", os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(other)
        dir_fd = os.open(up, os.O_RDONLY | os.O_DIRECTORY)
        try:
            # `fd` is victim.txt; ask to clean up the *name* decoy.txt.
            _up.unlink_if_same(dir_fd, "decoy.txt", fd)
        finally:
            os.close(dir_fd)
        assert (up / "decoy.txt").exists(), "cleanup deleted a file it did not own"
    finally:
        os.close(fd)


def test_the_upload_holds_no_descriptors_afterwards(client, project):
    """Descriptors are the thing a slow caller was able to hoard."""
    before = len(os.listdir("/proc/self/fd"))
    for i in range(12):
        assert _post(client, b"x" * 100, name=f"fd{i}.bin").status_code == 200
    after = len(os.listdir("/proc/self/fd"))
    assert after - before < 5, f"descriptors leaked: {before} -> {after}"


def test_a_body_that_never_starts_is_cut_off_too(client, project, monkeypatch):
    """The classic slowloris: headers, then nothing. A deadline checked per
    chunk never fires -- the read is parked awaiting a first chunk that never
    comes, holding two descriptors while it waits."""
    monkeypatch.setattr(_srv, "_UPLOAD_TIMEOUT", 0.2)

    def silence():
        import time
        time.sleep(3)      # not one byte, for far longer than the deadline
        yield b"x"

    # Wall clock here would measure the test client, not the server: httpx
    # finishes feeding the generator before it reads the response, so the
    # elapsed time includes the sleep whether or not the server gave up early.
    # The status is the discriminator -- without the deadline the byte arrives
    # at three seconds and the upload succeeds.
    r = client.post("/api/sessions/demo/upload?filename=quiet.bin",
                    content=silence(), headers=_AUTH)
    assert r.status_code == 408
    assert list((project / ".ctb-uploads").glob("quiet*")) == []


def test_too_many_at_once_is_told_to_come_back(client, project, monkeypatch):
    """Over the cap the answer is 'busy' rather than a wait, so nothing queues
    up holding descriptors."""
    monkeypatch.setattr(_srv, "_UPLOAD_CONCURRENCY", 0)
    r = _post(client, b"x")
    assert r.status_code == 503


def test_the_in_flight_count_returns_to_zero(client, project):
    """A permit that is not given back lowers the cap permanently."""
    for i in range(5):
        _post(client, b"x", name=f"c{i}.bin")
    assert _srv._upload_inflight == 0


# --- cancellation, driven for real ------------------------------------------
#
# TestClient cannot show any of this: it calls request.read(), which buffers a
# generator body and blocks the event loop, so a "slow" body is not slow from
# the server's side at all -- it simply arrives late, all at once. These drive
# the app through an ASGI transport on a real loop with a real async body, so
# the server is genuinely waiting and can genuinely be cancelled.

def _run(coro):
    """asyncio.run, so no pytest-asyncio plugin is needed for four tests."""
    return asyncio.run(coro)


async def _async_client():
    import httpx
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                             base_url="http://ctb.test", timeout=30)


async def _slow_body(chunks, gap):
    for c in chunks:
        await asyncio.sleep(gap)
        yield c


def _fds():
    return set(os.listdir("/proc/self/fd"))


def test_silence_is_cut_off_promptly_not_when_the_body_finally_comes(
        client, project, monkeypatch):
    """The classic slowloris: headers, then nothing. A per-chunk deadline never
    fires here -- the read is parked awaiting a first chunk, holding two
    descriptors, and the check is on the far side of that await."""
    monkeypatch.setattr(_srv, "_UPLOAD_TIMEOUT", 0.3)

    async def go():
        c = await _async_client()
        async with c:
            began = asyncio.get_running_loop().time()
            r = await c.post("/api/sessions/demo/upload?filename=quiet.bin",
                             content=_slow_body([b"x"], 10), headers=_AUTH)
            return r.status_code, asyncio.get_running_loop().time() - began

    status, elapsed = _run(go())
    assert status == 408
    # The real assertion: it gave up on its own schedule, not the sender's.
    assert elapsed < 3, f"waited {elapsed:.1f}s for a 0.3s deadline"
    assert list((project / ".ctb-uploads").glob("quiet*")) == []


def test_a_cancelled_upload_leaves_nothing_behind(client, project, monkeypatch):
    """Cancellation mid-body: no descriptor, no reservation, no partial file,
    no permanently consumed slot. This is the shape that survived three
    rewrites -- a resource acquired inside an executor whose await never
    resumed had nobody to release it."""
    monkeypatch.setattr(_up, "MAX_DIR_BYTES", 10_000)
    before_fds = _fds()

    async def go():
        c = await _async_client()
        async with c:
            task = asyncio.create_task(c.post(
                "/api/sessions/demo/upload?filename=cancelled.bin",
                content=_slow_body([b"a" * 50, b"b" * 50, b"c" * 50], 0.25),
                headers=_AUTH))
            await asyncio.sleep(0.35)      # one chunk in, two to go
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)

    _run(go())

    leaked = _fds() - before_fds
    assert not leaked, f"descriptors left open: {leaked}"
    assert _up._reservations == {}, f"quota reservation leaked: {_up._reservations}"
    assert _srv._upload_inflight == 0, "an upload slot was consumed permanently"
    assert list((project / ".ctb-uploads").glob("cancelled*")) == [], \
        "a partial file from a cancelled upload survived"


def test_repeated_cancellation_does_not_eat_the_quota(client, project, monkeypatch):
    """A leaked reservation is invisible -- the folder looks empty and every
    upload is refused until the process restarts."""
    monkeypatch.setattr(_up, "MAX_DIR_BYTES", 10_000)

    async def go():
        c = await _async_client()
        async with c:
            for _ in range(4):
                task = asyncio.create_task(c.post(
                    "/api/sessions/demo/upload?filename=x.bin",
                    content=_slow_body([b"a" * 20, b"b" * 20], 0.25),
                    headers=_AUTH))
                await asyncio.sleep(0.3)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            await asyncio.sleep(0.05)

    _run(go())
    assert _up._reservations == {}
    # And the folder still accepts an upload afterwards.
    assert _post(client, b"still works", name="after.txt").status_code == 200


def test_a_timed_out_upload_releases_its_reservation(client, project, monkeypatch):
    monkeypatch.setattr(_srv, "_UPLOAD_TIMEOUT", 0.3)
    monkeypatch.setattr(_up, "MAX_DIR_BYTES", 10_000)

    async def go():
        c = await _async_client()
        async with c:
            r = await c.post("/api/sessions/demo/upload?filename=slow2.bin",
                             content=_slow_body([b"x" * 10], 5), headers=_AUTH)
            return r.status_code

    assert _run(go()) == 408
    assert _up._reservations == {}
    assert _srv._upload_inflight == 0
