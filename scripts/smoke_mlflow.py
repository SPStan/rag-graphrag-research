from pathlib import Path

import mlflow


ROOT = Path(__file__).resolve().parents[1]
TRACKING_URI = "http://127.0.0.1:5000"
EXPERIMENT_NAME = "rag-graphrag-smoke"


def main() -> None:
    mlflow.set_tracking_uri(TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="smoke-test-no-llm") as run:
        mlflow.log_param("mode", "mock")
        mlflow.log_param("llm_calls", 0)
        mlflow.log_param("retrieval_method", "none")
        mlflow.log_metric("toy_score", 1.0)
        mlflow.set_tag("project", "rag-graphrag")
        mlflow.set_tag("purpose", "local-smoke-test")

        print({
            "status": "verified",
            "experiment": EXPERIMENT_NAME,
            "run_id": run.info.run_id,
            "tracking_uri": TRACKING_URI,
            "llm_calls": 0,
        })


if __name__ == "__main__":
    main()
