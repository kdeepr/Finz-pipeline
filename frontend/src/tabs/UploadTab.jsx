import { useEffect, useState } from "react";
import { api } from "../api";

export function UploadTab() {
  const [profiles, setProfiles] = useState([]);
  const [profileId, setProfileId] = useState("");
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [batches, setBatches] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [lastResult, setLastResult] = useState(null);

  const refresh = () => {
    api.listMappingProfiles().then(setProfiles).catch((e) => setError(e.message));
    api.listUploads().then(setBatches).catch((e) => setError(e.message));
  };

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (profiles.length && !profileId) setProfileId(profiles[0].id);
  }, [profiles]);

  const onFileChange = async (e) => {
    const f = e.target.files[0];
    setFile(f);
    setPreview(null);
    setError(null);
    if (f) {
      try {
        setPreview(await api.previewUpload(f));
      } catch (err) {
        setError(err.message);
      }
    }
  };

  const doUpload = async () => {
    if (!file || !profileId) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.createUpload(file, profileId);
      setLastResult(result);
      setFile(null);
      setPreview(null);
      refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div className="panel">
        <h3>Upload bank export</h3>
        <p className="muted">
          Accepts CSV or Excel exports. Column mapping is configurable per source (see Column Mapping
          Profiles below) - the parser never assumes a fixed column order.
        </p>
        {error && <div className="error-box">{error}</div>}
        <div className="row" style={{ marginBottom: "0.75rem" }}>
          <input type="file" accept=".csv,.xlsx,.xls" onChange={onFileChange} />
          <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button className="btn" disabled={!file || busy} onClick={doUpload}>
            {busy ? "Uploading..." : "Upload"}
          </button>
        </div>

        {preview && (
          <div style={{ overflowX: "auto" }}>
            <p className="muted">
              Preview: {preview.row_count} rows detected, columns: {preview.headers.join(", ")}
            </p>
          </div>
        )}

        {lastResult && (
          <div className="kpi-row">
            <div className="kpi">
              <div className="label">Rows</div>
              <div className="value">{lastResult.row_count}</div>
            </div>
            <div className="kpi">
              <div className="label">OK</div>
              <div className="value">{lastResult.ok_count}</div>
            </div>
            <div className="kpi">
              <div className="label">Duplicates</div>
              <div className="value">{lastResult.duplicate_count}</div>
            </div>
            <div className="kpi">
              <div className="label">Needs review</div>
              <div className="value">{lastResult.needs_review_count}</div>
            </div>
          </div>
        )}
      </div>

      <div className="panel">
        <h3>Upload history</h3>
        <table>
          <thead>
            <tr>
              <th>File</th>
              <th>Mapping</th>
              <th className="num">Rows</th>
              <th className="num">OK</th>
              <th className="num">Duplicate</th>
              <th className="num">Needs review</th>
              <th>Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr key={b.id}>
                <td>{b.filename}</td>
                <td>{b.mapping_profile_name}</td>
                <td className="num">{b.row_count}</td>
                <td className="num">{b.ok_count}</td>
                <td className="num">{b.duplicate_count}</td>
                <td className="num">{b.needs_review_count}</td>
                <td>{new Date(b.uploaded_at).toLocaleString()}</td>
              </tr>
            ))}
            {batches.length === 0 && (
              <tr>
                <td colSpan={7} className="muted">
                  No uploads yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
