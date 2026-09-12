# Seat 2/3 review — 7816d14

CHANGES for HttpWorkroomTransport mutation response handling. Fixed routes,
auth/session/CSRF and hosted normalized preview/start use the existing gateway.
Nineteen owner TUI tests pass at the exact archive, but independent MockTransport
controls found two uncovered cases (no model/network calls):

- A sent start POST followed by ReadError or RemoteProtocolError reports
  provider_unavailable instead of UncertainOutcome. The server may have applied
  the request; preserve the one-attempt rule and require recovery before another
  action, just as for a timeout.
- HTTP200 with a non-JSON body is returned as {} success. Reject malformed or
  non-object successful responses; for mutations report an unknown outcome.
  A read must likewise not substitute empty evidence for an invalid response.

Each reproduction made exactly one start POST. No automatic retry defect was
observed; the missing distinction is whether the action outcome is known.
Board #28469 carries these findings. Evidence-model and sanitizer review is 3/3's.
