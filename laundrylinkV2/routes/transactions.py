from flask import Blueprint, jsonify
from database import get_recent_transactions

transactions_bp = Blueprint("transactions", __name__)


@transactions_bp.route("/transactions", methods=["GET"])
def list_transactions():
    transactions = get_recent_transactions(limit=50)
    return jsonify(transactions)
