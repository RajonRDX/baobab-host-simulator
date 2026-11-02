"""
rules_evaluator.py — Whitelist AST Expression Evaluator & Context Builder
Executes custom authorizer rule expressions safely without using eval() or exec().
"""

import ast
from decimal import Decimal
from typing import Any, Dict, List, Optional


class SafeEvalError(Exception):
    """Raised when an expression contains forbidden nodes or syntax errors."""


class SafeAstEvaluator:
    ALLOWED_OPERATORS = {
        ast.Eq: lambda a, b: a == b,
        ast.NotEq: lambda a, b: a != b,
        ast.Lt: lambda a, b: a < b,
        ast.LtE: lambda a, b: a <= b,
        ast.Gt: lambda a, b: a > b,
        ast.GtE: lambda a, b: a >= b,
        ast.In: lambda a, b: a in b,
        ast.NotIn: lambda a, b: a not in b,
        ast.And: lambda a, b: a and b,
        ast.Or: lambda a, b: a or b,
        ast.Not: lambda a: not a,
    }

    @classmethod
    def evaluate(cls, expression: str, context: Dict[str, Any]) -> bool:
        clean_expr = expression.strip()
        if not clean_expr:
            return False
        try:
            tree = ast.parse(clean_expr, mode="eval")
            return bool(cls._eval_node(tree.body, context))
        except Exception as exc:
            raise SafeEvalError(f"Rule evaluation error in '{clean_expr}': {exc}")

    @classmethod
    def _eval_node(cls, node: ast.AST, context: Dict[str, Any]) -> Any:
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            key = node.id
            if key == "true":
                return True
            if key == "false":
                return False
            if key == "null" or key == "none":
                return None
            if key in context:
                return context[key]
            raise SafeEvalError(f"Undefined variable in rule context: '{key}'")

        if isinstance(node, ast.Attribute):
            attr = node.attr
            if attr.startswith("_"):
                raise SafeEvalError(f"Forbidden private/dunder attribute access: '{attr}'")
            val = cls._eval_node(node.value, context)
            if isinstance(val, dict):
                return val.get(attr)
            if hasattr(val, attr):
                return getattr(val, attr)
            raise SafeEvalError(f"Cannot resolve attribute '{attr}' on {type(val)}")

        if isinstance(node, (ast.List, ast.Tuple)):
            return [cls._eval_node(elt, context) for elt in node.elts]

        if isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type in cls.ALLOWED_OPERATORS:
                operand = cls._eval_node(node.operand, context)
                return cls.ALLOWED_OPERATORS[op_type](operand)
            raise SafeEvalError(f"Forbidden unary operator: {op_type}")

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for val_node in node.values:
                    if not cls._eval_node(val_node, context):
                        return False
                return True
            if isinstance(node.op, ast.Or):
                for val_node in node.values:
                    if cls._eval_node(val_node, context):
                        return True
                return False
            raise SafeEvalError(f"Forbidden boolean operator: {type(node.op)}")

        if isinstance(node, ast.Compare):
            left = cls._eval_node(node.left, context)
            for op, comparator_node in zip(node.ops, node.comparators):
                op_type = type(op)
                right = cls._eval_node(comparator_node, context)
                if op_type not in cls.ALLOWED_OPERATORS:
                    raise SafeEvalError(f"Forbidden comparison operator: {op_type}")
                # Numeric type coercion for comparisons
                if isinstance(left, (int, float, Decimal)) and isinstance(right, (int, float, Decimal)):
                    left_cmp = float(left)
                    right_cmp = float(right)
                else:
                    left_cmp = left
                    right_cmp = right

                if not cls.ALLOWED_OPERATORS[op_type](left_cmp, right_cmp):
                    return False
                left = right
            return True

        raise SafeEvalError(f"Forbidden syntax node: {type(node).__name__}")


def build_rule_context(
    mti: str,
    fields: Dict[str, str],
    tx_code: str,
    tx_amount: Decimal,
    card: Any = None,
    customer: Any = None,
    account: Any = None,
    issuer_inst: Any = None,
    acquirer_inst: Any = None,
    ps_code: str = "ITCL",
    card_limit: Any = None,
) -> Dict[str, Any]:
    """Constructs a normalized dictionary containing all transaction parameters for rule evaluation."""
    pan = fields.get("2", "")
    bin_prefix = pan[:6] if len(pan) >= 6 else ""

    inst_code = ""
    inst_name = ""
    if issuer_inst:
        inst_code = issuer_inst.institution_code
        inst_name = issuer_inst.name
    elif card and hasattr(card, "institution") and card.institution:
        inst_code = card.institution.institution_code
        inst_name = card.institution.name

    acq_code = acquirer_inst.institution_code if acquirer_inst else ""
    hour = int(fields.get("12", "120000")[:2]) if len(fields.get("12", "")) >= 2 else 12

    return {
        "trancode": str(tx_code),
        "tran_code": str(tx_code),
        "mti": str(mti),
        "amount": float(tx_amount),
        "currency": fields.get("49", "BDT"),
        "pan": pan,
        "bin": bin_prefix,
        "mcc": fields.get("18", "5411"),
        "terminal_id": fields.get("41", ""),
        "merchant_id": fields.get("32", ""),
        "institution": {
            "code": inst_code,
            "name": inst_name,
        },
        "acquirer_bank": acq_code,
        "issuer_bank": inst_code,
        "ps_name": ps_code,
        "channel": fields.get("25", "00"),
        "hour": hour,
        "card_status": card.card_status if card else "ACTIVE",
        "account_balance": float(account.available_balance) if account else 0.0,
        "daily_used": float(card_limit.daily_used) if card_limit else 0.0,
        "is_foreign": fields.get("19", "050") != "050",
    }
