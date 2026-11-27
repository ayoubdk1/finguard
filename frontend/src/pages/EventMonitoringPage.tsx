import type { EventMonitoringResponse } from '../services/api'

function formatMonitoringDate(timestamp: string | null): string {
  if (!timestamp) {
    return '\u2014'
  }
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) {
    return 'Invalid date'
  }
  return date.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

interface EventMonitoringPageProps {
  eventMonitoring: EventMonitoringResponse | null
  eventMonitoringLoading: boolean
  eventMonitoringError: string | null
  onRefresh: () => void
}

export function EventMonitoringPage({
  eventMonitoring,
  eventMonitoringLoading,
  eventMonitoringError,
  onRefresh,
}: EventMonitoringPageProps) {
  return (
          <section className="events-page">
            {/* HEADER */}

            <div className="events-page-header">
              <div>
                <h2>Event Stream Monitoring</h2>

                <p>
                  Track PostgreSQL outbox publication and consumer
                  processing.
                </p>
              </div>

              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  onRefresh()
                }}
              >
                ↻ Refresh
              </button>
            </div>

            {/* LOADING AND ERROR MESSAGES */}

            {eventMonitoringLoading && (
              <p className="events-message">
                Loading event monitoring data...
              </p>
            )}

            {eventMonitoringError && (
              <p className="transfer-error" role="alert">
                Monitoring API error: {eventMonitoringError}
                {eventMonitoring
                  ? ' Displaying the last successfully retrieved data.'
                  : ''}
              </p>
            )}

            {/* EVENT STATISTICS */}

            {eventMonitoring && (
              <>
                <div className="events-stats-grid">
                  <div className="events-stat-card">
                    <span>Total Events</span>

                    <h2>{eventMonitoring.total_events}</h2>

                    <p>Created in PostgreSQL outbox</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Pending Events</span>

                    <h2 className="events-pending-number">
                      {eventMonitoring.pending_events}
                    </h2>

                    <p>Awaiting successful publication</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Published Events</span>

                    <h2 className="events-published-number">
                      {eventMonitoring.published_events}
                    </h2>

                    <p>Publication recorded</p>
                  </div>

                  <div className="events-stat-card">
                    <span>Processed Events</span>

                    <h2 className="events-processed-number">
                      {eventMonitoring.processed_events}
                    </h2>

                    <p>Recorded by the consumer</p>
                  </div>
                </div>

                {/* EVENT PIPELINE */}

                <div className="panel events-pipeline-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Event Processing Pipeline</h3>
                      <p>FinGuard event-driven architecture</p>
                    </div>
                  </div>

                  <div className="events-pipeline">
                    <div className="pipeline-node">
                      <strong>PostgreSQL</strong>
                      <span>Transactional Outbox</span>
                    </div>

                    <span className="pipeline-arrow" aria-hidden="true">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M5 12h14" />
                        <path d="m12 5 7 7-7 7" />
                      </svg>
                    </span>

                    <div className="pipeline-node">
                      <strong>Redpanda</strong>
                      <span>Event Streaming</span>
                    </div>

                    <span className="pipeline-arrow" aria-hidden="true">
                      <svg
                        width="20"
                        height="20"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M5 12h14" />
                        <path d="m12 5 7 7-7 7" />
                      </svg>
                    </span>

                    <div className="pipeline-node">
                      <strong>Consumer</strong>
                      <span>Idempotent Processing</span>
                    </div>
                  </div>

                  <p className="events-pipeline-note">
                    Architecture overview. The counters above come from
                    PostgreSQL, not from live broker health checks.
                  </p>
                </div>

                {/* EVENT HISTORY */}

                <div className="panel events-history-panel">
                  <div className="panel-header">
                    <div>
                      <h3>Recent Events</h3>
                      <p>Latest outbox events from PostgreSQL</p>
                    </div>

                    <span className="panel-tag">
                      {eventMonitoringError
                        ? 'STALE DATA'
                        : 'LIVE DATA'}
                    </span>
                  </div>

                  <div className="table-wrapper">
                    <table className="events-table">
                      <thead>
                        <tr>
                          <th>EVENT ID</th>
                          <th>TRANSACTION ID</th>
                          <th>EVENT TYPE</th>
                          <th>CREATED AT</th>
                          <th>PUBLISHED AT</th>
                          <th>PROCESSED AT</th>
                          <th>STATUS</th>
                          <th>ATTEMPTS</th>
                        </tr>
                      </thead>

                      <tbody>
                        {eventMonitoring.recent_events.length === 0 ? (
                          <tr>
                            <td colSpan={8}>No events found.</td>
                          </tr>
                        ) : (
                          eventMonitoring.recent_events.map((event) => (
                            <tr key={event.event_id}>
                              <td>
                                <span
                                  className="transaction-id"
                                  title={event.event_id}
                                >
                                  {event.event_id.slice(0, 8)}...
                                </span>
                              </td>

                              <td>
                                <span
                                  className="transaction-id"
                                  title={event.aggregate_id}
                                >
                                  {event.aggregate_id.slice(0, 8)}...
                                </span>
                              </td>

                              <td>
                                <strong
                                  style={{
                                    color: 'var(--color-foreground)',
                                  }}
                                >
                                  {event.event_type}
                                </strong>
                              </td>

                              <td>
                                {formatMonitoringDate(event.created_at)}
                              </td>

                              <td>
                                {formatMonitoringDate(
                                  event.published_at
                                )}
                              </td>

                              <td>
                                {formatMonitoringDate(
                                  event.processed_at
                                )}
                              </td>

                              <td>
                                <span
                                  className={`events-status events-status-${event.status.toLowerCase()}`}
                                >
                                  {event.status}
                                </span>
                              </td>

                              <td>{event.publish_attempts}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>

                  <p className="events-table-note">
                    Row statuses represent outbox publication. Consumer
                    processing is reported separately in the Processed
                    Events counter.
                  </p>
                </div>

                {/* AUTOMATIC REFRESH */}

                <p className="events-refresh-note">
                  <span className="indicator-dot" aria-hidden="true" />
                  Automatically refreshes every 10 seconds while this
                  page is open.
                </p>
              </>
            )}
          </section>
  )
}
