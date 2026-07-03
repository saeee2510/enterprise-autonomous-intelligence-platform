import uuid
import time
import json
import psycopg2


class ExecutionLogger:

    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()

    def new_trace_id(self):
        return str(uuid.uuid4())

    def log_step(
        self,
        trace_id: str,
        query: str,
        step: str,
        input_data,
        output_data,
        latency_ms: float,
        success: bool = True
    ):
        self.cur.execute(
            """
            INSERT INTO execution_logs (
                query,
                trace_id,
                step,
                input,
                output,
                latency_ms,
                success
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                query,
                trace_id,
                step,
                json.dumps(input_data),
                json.dumps(output_data),
                latency_ms,
                success
            )
        )
        self.conn.commit()

    def time_block(self):
        return time.time()