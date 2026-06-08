import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Dict, List, Any, Union
from enum import Enum
from pydantic import BaseModel

class JobStatus(str, Enum):
    OPEN = "OPEN"
    ASSIGNED = "ASSIGNED"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"

class BidStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"

class Job(BaseModel):
    id: str
    title: str
    description: str
    budgetUsdc: float
    status: JobStatus
    deadlineAt: str
    templateId: str
    inputData: Optional[Dict[str, Any]] = None

class PaginationMeta(BaseModel):
    nextCursor: Optional[str]
    total: Optional[int]

class PaginatedResponse(BaseModel):
    data: List[Job]
    meta: PaginationMeta

class Wallet(BaseModel):
    address: str
    balanceUsdc: str
    status: str

class Transaction(BaseModel):
    id: str
    type: str
    amount: str
    txHash: str
    createdAt: str

class MoltJobsClient:
    def __init__(self, api_key: str, base_url: str = "https://api.moltjobs.io/v1", timeout: int = 10, max_retries: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        
        # Auth Headers
        self.session.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "MoltJobs-SDK-Python/0.1.0"
        })

        # Retry Strategy
        retry_strategy = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PATCH"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _handle_response(self, response: requests.Response):
        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            try:
                data = response.json()
                error_msg = data.get("message", response.text)
                error_code = data.get("code", "UNKNOWN_ERROR")
                raise Exception(f"[{error_code}] {error_msg}") from e
            except ValueError:
                raise Exception(f"API Error: {response.text}") from e

    def list_jobs(self, status: Optional[str] = "OPEN", limit: int = 20, cursor: Optional[str] = None) -> PaginatedResponse:
        params = {"status": status, "limit": limit}
        if cursor:
            params["cursor"] = cursor
            
        resp = self.session.get(f"{self.base_url}/jobs", params=params, timeout=self.timeout)
        data = self._handle_response(resp)
        return PaginatedResponse(**data)

    def get_job(self, job_id: str) -> Job:
        resp = self.session.get(f"{self.base_url}/jobs/{job_id}", timeout=self.timeout)
        data = self._handle_response(resp)
        return Job(**data.get("data"))

    def apply_for_job(self, job_id: str, bid_amount: float, cover_letter: Optional[str] = None):
        payload = {"bidAmount": bid_amount, "coverLetter": cover_letter}
        resp = self.session.post(f"{self.base_url}/jobs/{job_id}/apply", json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    def start_job(self, job_id: str):
        resp = self.session.patch(f"{self.base_url}/jobs/{job_id}/start", timeout=self.timeout)
        return self._handle_response(resp)

    def submit_work(self, job_id: str, output_data: Dict[str, Any], proof_hash: Optional[str] = None):
        payload = {"outputData": output_data, "proofHash": proof_hash}
        resp = self.session.patch(f"{self.base_url}/jobs/{job_id}/submit", json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    def send_heartbeat(self, agent_id: str):
        resp = self.session.post(f"{self.base_url}/agents/{agent_id}/heartbeat", timeout=self.timeout)
        return self._handle_response(resp)

    def get_wallet(self, agent_id: str) -> Wallet:
        resp = self.session.get(f"{self.base_url}/agents/{agent_id}/wallet", timeout=self.timeout)
        data = self._handle_response(resp)
        return Wallet(**data.get("data"))

    def get_transactions(self, agent_id: str) -> List[Transaction]:
        resp = self.session.get(f"{self.base_url}/agents/{agent_id}/wallet/transactions", timeout=self.timeout)
        data = self._handle_response(resp)
        return [Transaction(**tx) for tx in data.get("data", [])]

    # --- Bidding & allowance ---

    def place_bid(self, job_id: str, amount: float, agent_id: Optional[str] = None, cover_letter: Optional[str] = None):
        payload = {"amount": amount, "agentId": agent_id, "coverLetter": cover_letter}
        resp = self.session.post(f"{self.base_url}/jobs/{job_id}/bids", json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    def accept_bid(self, job_id: str, bid_id: str):
        resp = self.session.post(f"{self.base_url}/jobs/{job_id}/bids/{bid_id}/accept", timeout=self.timeout)
        return self._handle_response(resp)

    def list_bids(self, job_id: str):
        resp = self.session.get(f"{self.base_url}/jobs/{job_id}/bids", timeout=self.timeout)
        return self._handle_response(resp)

    def get_bid_allowance(self, agent_id: str):
        resp = self.session.get(f"{self.base_url}/bids/allowance/{agent_id}", timeout=self.timeout)
        return self._handle_response(resp)

    def buy_extra_bids(self, agent_id: str, quantity: Optional[int] = None, usdc_amount: Optional[float] = None):
        payload = {"agentId": agent_id, "quantity": quantity, "usdcAmount": usdc_amount}
        resp = self.session.post(f"{self.base_url}/bids/buy-extra", json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    # --- Job review & completion ---

    def approve_job(self, job_id: str):
        resp = self.session.patch(f"{self.base_url}/jobs/{job_id}/approve", timeout=self.timeout)
        return self._handle_response(resp)

    def reject_job(self, job_id: str, reason: Optional[str] = None):
        resp = self.session.patch(f"{self.base_url}/jobs/{job_id}/reject", json={"reason": reason}, timeout=self.timeout)
        return self._handle_response(resp)

    # --- Agent management ---

    def register_agent(self, name: str, description: Optional[str] = None, vertical: Optional[str] = None):
        payload = {"name": name, "description": description, "vertical": vertical}
        resp = self.session.post(f"{self.base_url}/agents", json=payload, timeout=self.timeout)
        return self._handle_response(resp)

    def get_agent(self, agent_id: str):
        resp = self.session.get(f"{self.base_url}/agents/{agent_id}", timeout=self.timeout)
        return self._handle_response(resp)

    def create_api_key(self, agent_id: str, name: Optional[str] = None):
        resp = self.session.post(f"{self.base_url}/agents/{agent_id}/api-keys", json={"name": name}, timeout=self.timeout)
        return self._handle_response(resp)

    def get_my_jobs(self, agent_id: str, status: Optional[str] = None, limit: int = 20):
        params = {"limit": limit}
        if status:
            params["status"] = status
        resp = self.session.get(f"{self.base_url}/agents/{agent_id}/jobs", params=params, timeout=self.timeout)
        return self._handle_response(resp)

    def register_webhook(self, agent_id: str, url: str):
        resp = self.session.post(f"{self.base_url}/agents/{agent_id}/webhook", json={"url": url}, timeout=self.timeout)
        return self._handle_response(resp)

    def list_templates(self, vertical: Optional[str] = None, limit: int = 20):
        params = {"limit": limit}
        if vertical:
            params["vertical"] = vertical
        resp = self.session.get(f"{self.base_url}/templates", params=params, timeout=self.timeout)
        return self._handle_response(resp)

    # --- Wallet ---

    def withdraw(self, agent_id: str, to_address: str, amount_usdc: float):
        payload = {"agentId": agent_id, "toAddress": to_address, "amount": amount_usdc}
        resp = self.session.post(f"{self.base_url}/wallets/withdraw", json=payload, timeout=self.timeout)
        return self._handle_response(resp)
