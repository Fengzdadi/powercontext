// Runtime configuration, all overridable through environment variables.
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const env = process.env;
const int = (v, d) => (v === undefined || v === "" ? d : Number.parseInt(v, 10));

export const config = {
  port: int(env.PORT, 5280),
  host: env.HOST || "127.0.0.1",
  seekdb: {
    // Server mode (default): a local seekdb started by scripts/seekdb-docker.sh.
    host: env.SEEKDB_HOST || "127.0.0.1",
    port: int(env.SEEKDB_PORT, 12881),
    user: env.SEEKDB_USER || "root",
    password: env.SEEKDB_PASSWORD || "",
    database: env.SEEKDB_DATABASE || "stepfun_kb",
    // Embedded mode: set SEEKDB_PATH to a directory and seekdb-js opens it in-process instead.
    path: env.SEEKDB_PATH || "",
  },
  // How long a write waits for the async vector index before falling back to an explicit refresh.
  visibilityTimeoutMs: int(env.VISIBILITY_TIMEOUT_MS, 5000),
  modelsDir: path.join(ROOT, "models"),
  benchResultsDir: path.join(ROOT, "bench", "results"),
};
