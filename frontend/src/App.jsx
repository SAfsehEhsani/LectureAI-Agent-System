import { useState, useEffect, useRef } from "react";
import axios from "axios";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API = (import.meta.env.VITE_API_URL || "/api").replace(/\/+$/, "");

function App() {
  const [tab, setTab] = useState("youtube");
  const [url, setUrl] = useState("");
  const [videoFile, setVideoFile] = useState(null);
  const [transcriptFile, setTranscriptFile] = useState(null);
  const [rawText, setRawText] = useState("");

  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const [resultTab, setResultTab] = useState("chapters");

  // Interactive Quiz state
  const [selectedAnswers, setSelectedAnswers] = useState({});
  const [showAllAnswers, setShowAllAnswers] = useState(false);

  // Clip rendering & feedback state
  const [cuttingClipIdx, setCuttingClipIdx] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");

  // History & Proofs Storage state
  const [history, setHistory] = useState([]);
  const [showHistoryModal, setShowHistoryModal] = useState(false);
  const [proofModalText, setProofModalText] = useState(null);
  const [loadingHistoryId, setLoadingHistoryId] = useState(null);

  const videoPlayerRef = useRef(null);

  // Load history list on startup
  useEffect(() => {
    fetchHistory();
  }, []);

  async function fetchHistory() {
    try {
      const res = await axios.get(`${API}/history`);
      if (Array.isArray(res.data)) {
        setHistory(res.data);
      }
    } catch {
      // Backend history might not be ready yet
    }
  }

  // Load sample lecture
  async function loadSampleLecture() {
    setError("");
    setLoading(true);
    setStatus("Loading 60-min CS229 sample lecture...");
    try {
      const res = await axios.get(`${API}/sample`);
      if (res.data?.content) {
        setTab("paste");
        setRawText(res.data.content);
        setStatus("Sample loaded! Click 'Generate Complete Learning Pack' to process.");
      } else {
        setUrl("https://www.youtube.com/watch?v=ZA-tUyM_y7s");
        setTab("youtube");
      }
    } catch {
      setUrl("https://www.youtube.com/watch?v=ZA-tUyM_y7s");
      setTab("youtube");
    } finally {
      setLoading(false);
    }
  }

  function fillYouTubeExample(exampleUrl) {
    setUrl(exampleUrl);
    setTab("youtube");
    setError("");
  }

  async function submit() {
    setError("");
    setResult(null);
    setSelectedAnswers({});
    setShowAllAnswers(false);
    setLoading(true);

    try {
      let res;
      if (tab === "youtube") {
        setStatus("Fetching YouTube captions & extracting speech segments...");
        const fd = new FormData();
        fd.append("url", url.trim());
        res = await axios.post(`${API}/generate/youtube`, fd);
      } else if (tab === "upload") {
        setStatus("Uploading video and running speech-to-text with Whisper...");
        const fd = new FormData();
        fd.append("file", videoFile);
        res = await axios.post(`${API}/generate/upload`, fd, { timeout: 0 });
      } else if (tab === "transcript") {
        setStatus("Parsing transcript file and synthesizing learning pack via Groq...");
        const fd = new FormData();
        fd.append("file", transcriptFile);
        res = await axios.post(`${API}/generate/transcript`, fd);
      } else {
        setStatus("Parsing text and synthesizing learning pack via Groq...");
        const blob = new Blob([rawText], { type: "text/plain" });
        const fd = new FormData();
        fd.append("file", blob, "pasted_transcript.txt");
        res = await axios.post(`${API}/generate/transcript`, fd);
      }

      setResult(res.data);
      setResultTab("chapters");
      fetchHistory(); // Refresh history with new proof
    } catch (e) {
      if (e.response?.status === 405) {
        setError("⚠️ 405 Method Not Allowed: Frontend is not connected to the backend. In Vercel Settings -> Environment Variables, add VITE_API_URL pointing to your Railway backend URL (e.g. https://your-app.up.railway.app) and Redeploy.");
      } else {
        setError(e.response?.data?.detail || e.message || "Failed to process lecture.");
      }
    } finally {
      setLoading(false);
      setStatus("");
    }
  }

  // Load a saved learning pack from storage
  async function loadFromHistory(packId) {
    setLoadingHistoryId(packId);
    try {
      const res = await axios.get(`${API}/history/${packId}`);
      if (res.data) {
        setResult(res.data);
        setResultTab("chapters");
        setSelectedAnswers({});
        setShowAllAnswers(false);
        setShowHistoryModal(false);
      }
    } catch (e) {
      alert("Failed to load saved pack: " + (e.response?.data?.detail || e.message));
    } finally {
      setLoadingHistoryId(null);
    }
  }

  // Delete a saved learning pack
  async function deleteFromHistory(packId) {
    if (!confirm("Are you sure you want to delete this saved proof record?")) return;
    try {
      await axios.delete(`${API}/history/${packId}`);
      setHistory(prev => prev.filter(p => p.id !== packId));
    } catch (e) {
      alert("Delete failed: " + (e.response?.data?.detail || e.message));
    }
  }

  // View audit proof certificate in modal
  async function viewProofCertificate(packId) {
    try {
      const res = await axios.get(`${API}/history/${packId}/proof`);
      setProofModalText(res.data);
    } catch (e) {
      alert("Could not load proof certificate: " + (e.response?.data?.detail || e.message));
    }
  }

  // Download audit proof certificate file
  async function downloadProofFile(packId) {
    try {
      const res = await axios.get(`${API}/history/${packId}/proof`, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([res.data], { type: "text/plain" }));
      a.download = `${packId}_audit_proof.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("Export failed: " + (e.response?.data?.detail || e.message));
    }
  }

  async function download(endpoint, mime, filename) {
    try {
      const res = await axios.post(`${API}${endpoint}`, result, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([res.data], { type: mime }));
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("Export failed: " + (e.response?.data?.detail || e.message));
    }
  }

  async function cutAndDownloadClip(clip, idx) {
    setCuttingClipIdx(idx);
    try {
      const fd = new FormData();
      if (result.video_path) {
        fd.append("video_path", result.video_path);
      }
      if (result.metadata?.source && (result.metadata.source.includes("youtube.com") || result.metadata.source.includes("youtu.be"))) {
        fd.append("source_url", result.metadata.source);
      }
      fd.append("start", clip.start);
      fd.append("end", clip.end);
      fd.append("title", clip.title);
      fd.append("segments_json", JSON.stringify(result.segments || []));

      const res = await axios.post(`${API}/clips/render`, fd, { responseType: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([res.data], { type: "video/mp4" }));
      a.download = `${clip.title.replace(/\s+/g, "_")}.mp4`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      alert("Clip cutting failed: " + (e.response?.data?.detail || e.message || "FFmpeg error"));
    } finally {
      setCuttingClipIdx(null);
    }
  }

  function copyToClipboard(text, msg = "Copied to clipboard!") {
    navigator.clipboard.writeText(text);
    setCopyFeedback(msg);
    setTimeout(() => setCopyFeedback(""), 2500);
  }

  function handleSelectOption(qIdx, opt) {
    if (showAllAnswers) return;
    setSelectedAnswers(prev => ({ ...prev, [qIdx]: opt }));
  }

  const quizScore = result?.quiz?.reduce((acc, q, idx) => {
    return acc + (selectedAnswers[idx] === q.answer ? 1 : 0);
  }, 0) || 0;

  const answeredCount = Object.keys(selectedAnswers).length;

  const canSubmit = !loading && (
    (tab === "youtube" && url.trim()) ||
    (tab === "upload" && videoFile) ||
    (tab === "transcript" && transcriptFile) ||
    (tab === "paste" && rawText.trim())
  );

  const ytMatch = result?.metadata?.source?.match(/(?:v=|\/embed\/|youtu\.be\/|\/shorts\/)([a-zA-Z0-9_-]{11})/);
  const ytVideoId = ytMatch ? ytMatch[1] : null;

  return (
    <div className="app">
      <header>
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
          <div className="brand-badge">⚡ AI Lecture Transformation Engine</div>
          <button
            id="btn-open-history"
            className="pill-btn"
            style={{ background: "rgba(16, 185, 129, 0.15)", borderColor: "rgba(16, 185, 129, 0.4)", color: "#6ee7b7" }}
            onClick={() => { fetchHistory(); setShowHistoryModal(true); }}
          >
            📜 Stored Proofs & History ({history.length})
          </button>
        </div>

        <h1 className="logo">LectureLens AI</h1>
        <p className="tagline">
          Convert 60+ minute lectures into timestamped chapters, study notes, interactive quizzes & video clips with audit verification.
        </p>

        <div className="quick-actions">
          <button id="btn-sample-lecture" className="pill-btn" onClick={loadSampleLecture} disabled={loading}>
            ⚡ Try 60-min CS229 Lecture Sample
          </button>
          <button id="btn-example-mit" className="pill-btn" onClick={() => fillYouTubeExample("https://www.youtube.com/watch?v=ZA-tUyM_y7s")}>
            🎓 MIT 6.006 Algorithms (YouTube)
          </button>
        </div>
      </header>

      <main>
        <div className="card">
          <div className="tabs-nav">
            {[
              { id: "youtube",    icon: "🔗", label: "YouTube URL" },
              { id: "upload",     icon: "📁", label: "Upload Video" },
              { id: "transcript", icon: "📄", label: "Upload Transcript" },
              { id: "paste",      icon: "✍️", label: "Paste Text" },
            ].map(({ id, icon, label }) => (
              <button
                key={id}
                id={`tab-${id}`}
                className={tab === id ? "tab-btn active" : "tab-btn"}
                onClick={() => { setTab(id); setError(""); }}
              >
                <span>{icon}</span> {label}
              </button>
            ))}
          </div>

          <div className="input-area">
            {tab === "youtube" && (
              <div>
                <label className="input-label" htmlFor="input-yt-url">
                  <span>Enter Lecture YouTube URL</span>
                  <span>Auto-extracts captions or transcribes audio</span>
                </label>
                <input
                  id="input-yt-url"
                  className="text-input"
                  placeholder="https://www.youtube.com/watch?v=..."
                  value={url}
                  onChange={e => setUrl(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && canSubmit && submit()}
                />
              </div>
            )}

            {tab === "upload" && (
              <label className="file-dropzone" id="dropzone-video">
                <input
                  type="file"
                  accept=".mp4,.mov,.mkv,.webm"
                  onChange={e => setVideoFile(e.target.files[0])}
                />
                <div className="dropzone-icon">📹</div>
                {videoFile ? (
                  <span className="file-selected-badge">✅ {videoFile.name} ({(videoFile.size / (1024 * 1024)).toFixed(1)} MB)</span>
                ) : (
                  <>
                    <div className="dropzone-text">Click or drag to upload lecture video</div>
                    <div className="dropzone-hint">Supports MP4, MOV, MKV, WebM (Groq Whisper Turbo + Faster-Whisper)</div>
                  </>
                )}
              </label>
            )}

            {tab === "transcript" && (
              <label className="file-dropzone" id="dropzone-transcript">
                <input
                  type="file"
                  accept=".srt,.vtt,.txt,.json"
                  onChange={e => setTranscriptFile(e.target.files[0])}
                />
                <div className="dropzone-icon">📜</div>
                {transcriptFile ? (
                  <span className="file-selected-badge">✅ {transcriptFile.name}</span>
                ) : (
                  <>
                    <div className="dropzone-text">Click or drag transcript file</div>
                    <div className="dropzone-hint">Supports SRT, WebVTT, JSON, and plain TXT</div>
                  </>
                )}
              </label>
            )}

            {tab === "paste" && (
              <div>
                <label className="input-label" htmlFor="input-raw-text">
                  <span>Paste Transcript or Lecture Text</span>
                  <span>{rawText ? `${rawText.split(/\s+/).filter(Boolean).length} words` : "Supports timestamps or plain text"}</span>
                </label>
                <textarea
                  id="input-raw-text"
                  className="text-area"
                  rows={6}
                  placeholder="Paste lecture transcript here (e.g. 00:00:00 Welcome to today's lecture...)"
                  value={rawText}
                  onChange={e => setRawText(e.target.value)}
                />
              </div>
            )}

            <button
              id="btn-generate"
              className="btn-primary"
              onClick={submit}
              disabled={!canSubmit}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  <span>Processing...</span>
                </>
              ) : (
                <>
                  <span>🚀</span>
                  <span>Generate Complete Learning Pack</span>
                </>
              )}
            </button>
          </div>

          {loading && status && (
            <div className="loading-indicator" style={{ marginTop: "1rem" }}>
              <span className="spinner" />
              <span>{status}</span>
            </div>
          )}

          {error && <div className="error-box" style={{ marginTop: "1rem" }}>⚠️ {error}</div>}
        </div>

        {/* Learning Pack Results */}
        {result && (
          <div className="card results-card" id="results-container">
            <div className="results-header">
              <div>
                <div className="results-title">
                  <span>📚</span>
                  <span>Learning Pack Generated</span>
                </div>
                {result.proof_hash && (
                  <div style={{ marginTop: "0.35rem" }}>
                    <span className="proof-hash-pill">
                      🔒 Audit Proof Hash: #{result.proof_hash}
                    </span>
                  </div>
                )}
              </div>

              <div className="meta-stats">
                <span className="stat-badge highlight">⏱ {result.metadata.duration_text}</span>
                <span className="stat-badge highlight">📝 {result.metadata.word_count.toLocaleString()} words</span>
                <span className="stat-badge">🤖 {result.metadata.generation_mode}</span>
                <span className="stat-badge">⚡ {result.metadata.processing_seconds}s</span>
                <span className="stat-badge">📡 {result.metadata.transcription_mode}</span>
              </div>
            </div>

            {/* Video preview if YouTube */}
            {ytVideoId && (
              <div className="video-preview-wrapper">
                <iframe
                  ref={videoPlayerRef}
                  className="video-frame"
                  src={`https://www.youtube.com/embed/${ytVideoId}`}
                  title="Lecture Video"
                  allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                  allowFullScreen
                />
              </div>
            )}

            {/* Sub-tabs for content */}
            <div className="content-tabs">
              {[
                { id: "chapters", icon: "📑", label: `Chapters (${result.chapters?.length || 0})` },
                { id: "notes",    icon: "📋", label: "Study Notes" },
                { id: "quiz",     icon: "❓", label: `Quiz (${result.quiz?.length || 0})` },
                { id: "clips",    icon: "✂️", label: `Short Clips (${result.clips?.length || 0})` },
              ].map(({ id, icon, label }) => (
                <button
                  key={id}
                  id={`subtab-${id}`}
                  className={resultTab === id ? "content-tab active" : "content-tab"}
                  onClick={() => setResultTab(id)}
                >
                  <span>{icon}</span> {label}
                </button>
              ))}
            </div>

            {/* Chapters Tab */}
            {resultTab === "chapters" && (
              <div className="chapters-grid" id="chapters-list">
                {result.chapters.map((c, i) => (
                  <div key={i} className="chapter-card">
                    <div className="chapter-header">
                      <span className="chapter-time">⏱ {c.start} – {c.end}</span>
                      <h3 className="chapter-title">{c.title}</h3>
                    </div>
                    <p className="chapter-summary">{c.summary}</p>
                    {c.key_points?.length > 0 && (
                      <ul className="key-points-list">
                        {c.key_points.map((p, j) => (
                          <li key={j}>{p}</li>
                        ))}
                      </ul>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Notes Tab */}
            {resultTab === "notes" && (
              <div>
                <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: "0.75rem" }}>
                  <button
                    className="pill-btn"
                    onClick={() => copyToClipboard(result.notes_markdown, "Notes copied to clipboard!")}
                  >
                    📋 Copy Markdown Notes
                  </button>
                </div>
                <div className="prose-notes" id="notes-content">
                  <ReactMarkdown>{result.notes_markdown}</ReactMarkdown>
                </div>
              </div>
            )}

            {/* Interactive Quiz Tab */}
            {resultTab === "quiz" && (
              <div className="quiz-container" id="quiz-list">
                <div className="quiz-score-banner">
                  <div className="score-text">
                    🎯 Interactive Practice Quiz — {answeredCount} of {result.quiz.length} answered
                  </div>
                  <div style={{ display: "flex", gap: "0.6rem", alignItems: "center" }}>
                    <span className="score-badge">Score: {quizScore} / {result.quiz.length}</span>
                    <button
                      className="pill-btn"
                      onClick={() => setShowAllAnswers(!showAllAnswers)}
                    >
                      {showAllAnswers ? "🙈 Hide Answers" : "💡 Reveal All Answers"}
                    </button>
                  </div>
                </div>

                {result.quiz.map((q, i) => {
                  const userChoice = selectedAnswers[i];
                  const hasAnswered = userChoice !== undefined;
                  const isCorrect = userChoice === q.answer;

                  return (
                    <div key={i} className="quiz-card" id={`quiz-q-${i + 1}`}>
                      <div className="quiz-question">
                        <span>Q{i + 1}. </span> {q.question}
                      </div>

                      <div className="quiz-options">
                        {q.options.map((opt, j) => {
                          let optClass = "quiz-option-btn";
                          if (userChoice === opt) {
                            optClass += opt === q.answer ? " selected-correct" : " selected-wrong";
                          } else if (showAllAnswers && opt === q.answer) {
                            optClass += " reveal-correct";
                          }

                          return (
                            <button
                              key={j}
                              className={optClass}
                              onClick={() => handleSelectOption(i, opt)}
                            >
                              <span>{String.fromCharCode(65 + j)}. {opt}</span>
                              {userChoice === opt && (
                                <span>{opt === q.answer ? "✅" : "❌"}</span>
                              )}
                              {showAllAnswers && opt === q.answer && userChoice !== opt && (
                                <span>✅ Correct</span>
                              )}
                            </button>
                          );
                        })}
                      </div>

                      {(hasAnswered || showAllAnswers) && (
                        <div className="quiz-feedback">
                          <div className="feedback-explanation">
                            <strong>{isCorrect ? "🎉 Correct!" : `Answer: ${q.answer}`}</strong> {q.explanation}
                          </div>
                          {q.evidence && (
                            <div className="feedback-evidence">
                              📌 <strong>Transcript Evidence:</strong> "{q.evidence}"
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Clips Tab */}
            {resultTab === "clips" && (
              <div className="clips-grid" id="clips-list">
                {result.clips.map((c, i) => (
                  <div key={i} className="clip-card" id={`clip-card-${i + 1}`}>
                    <div>
                      <span className="clip-time-tag">⏱ {c.start_text} – {c.end_text}</span>
                      <h4 className="clip-title">{c.title}</h4>
                      <p className="clip-reason">{c.reason}</p>
                    </div>

                    <button
                      className="btn-cut-clip"
                      onClick={() => cutAndDownloadClip(c, i)}
                      disabled={cuttingClipIdx === i}
                      title="Render video clip using FFmpeg"
                    >
                      {cuttingClipIdx === i ? (
                        <>
                          <span className="spinner" />
                          <span>Rendering MP4...</span>
                        </>
                      ) : (
                        <>
                          <span>✂️</span>
                          <span>Cut Clip with FFmpeg (MP4)</span>
                        </>
                      )}
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Export Toolbar */}
            <div className="export-toolbar">
              <div style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                💾 Export & Proofs:
              </div>
              <div className="export-group">
                {result.id && (
                  <button
                    id="btn-export-proof"
                    className="btn-action-outline"
                    style={{ borderColor: "rgba(16, 185, 129, 0.4)", color: "#6ee7b7" }}
                    onClick={() => downloadProofFile(result.id)}
                  >
                    📜 Proof Certificate (.txt)
                  </button>
                )}
                <button
                  id="btn-export-pdf"
                  className="btn-action-outline"
                  onClick={() => download("/export/pdf", "application/pdf", "learning_pack.pdf")}
                >
                  📄 Download PDF
                </button>
                <button
                  id="btn-export-md"
                  className="btn-action-outline"
                  onClick={() => download("/export/markdown", "text/markdown", "learning_pack.md")}
                >
                  📝 Download Markdown
                </button>
                <button
                  id="btn-export-json"
                  className="btn-action-outline"
                  onClick={() => download("/export/json", "application/json", "learning_pack.json")}
                >
                  💾 Download JSON
                </button>
              </div>
            </div>

            {copyFeedback && (
              <div style={{ marginTop: "0.75rem", color: "#34d399", fontSize: "0.85rem", textAlign: "right" }}>
                ✨ {copyFeedback}
              </div>
            )}
          </div>
        )}
      </main>

      {/* History & Stored Proofs Modal */}
      {showHistoryModal && (
        <div className="modal-overlay" onClick={() => setShowHistoryModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <span>📜</span>
                <span>Stored History & Audit Proofs ({history.length})</span>
              </div>
              <button className="modal-close-btn" onClick={() => setShowHistoryModal(false)}>✕</button>
            </div>

            <div className="modal-body">
              {history.length === 0 ? (
                <div style={{ textAlign: "center", color: "var(--text-muted)", padding: "2rem" }}>
                  No stored learning packs yet. Generate a lecture to create an audit record!
                </div>
              ) : (
                <div className="history-list">
                  {history.map(item => (
                    <div key={item.id} className="history-item-card">
                      <div className="history-item-top">
                        <span className="history-item-title">{item.source}</span>
                        <span className="proof-hash-pill">🔒 #{item.proof_hash}</span>
                      </div>

                      <div className="history-meta-row">
                        <span className="stat-badge highlight">⏱ {item.duration_text}</span>
                        <span className="stat-badge">📝 {item.word_count?.toLocaleString()} words</span>
                        <span className="stat-badge">📚 {item.chapters_count} Chapters</span>
                        <span className="stat-badge">❓ {item.quiz_count} Quiz</span>
                        <span className="stat-badge">🤖 {item.model}</span>
                        <span className="stat-badge">📅 {new Date(item.created_at).toLocaleString()}</span>
                      </div>

                      <div className="history-item-actions">
                        <button
                          className="btn-history-load"
                          onClick={() => loadFromHistory(item.id)}
                          disabled={loadingHistoryId === item.id}
                        >
                          {loadingHistoryId === item.id ? "Loading..." : "📂 Open Learning Pack"}
                        </button>
                        <button
                          className="btn-history-proof"
                          onClick={() => viewProofCertificate(item.id)}
                        >
                          📜 View Proof Receipt
                        </button>
                        <button
                          className="btn-history-proof"
                          onClick={() => downloadProofFile(item.id)}
                        >
                          ⬇ Download Certificate
                        </button>
                        <button
                          className="btn-history-delete"
                          onClick={() => deleteFromHistory(item.id)}
                          title="Delete from audit history"
                        >
                          🗑 Delete
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Proof Certificate Text Modal */}
      {proofModalText && (
        <div className="modal-overlay" onClick={() => setProofModalText(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <div className="modal-title">
                <span>🔒</span>
                <span>Official Audit & Proof Certificate</span>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  className="pill-btn"
                  onClick={() => copyToClipboard(proofModalText, "Certificate copied!")}
                >
                  📋 Copy
                </button>
                <button className="modal-close-btn" onClick={() => setProofModalText(null)}>✕</button>
              </div>
            </div>

            <div className="modal-body">
              <div className="certificate-box">
                {proofModalText}
              </div>
            </div>
          </div>
        </div>
      )}

      <footer>
        <p>LectureLens AI · Persistent SQLite Storage & SHA-256 Audit Proof System</p>
      </footer>
    </div>
  );
}

export default App;
