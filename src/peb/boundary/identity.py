"""Identity predicate shared by finite-v1 and continuous-operation monitors."""


def subject_scope_failure(
    run_id: str, session_id: str, expected_run: str, expected_session: str
) -> str | None:
    if run_id != expected_run:
        return "wrong_run"
    if session_id != expected_session:
        return "wrong_session"
    return None
