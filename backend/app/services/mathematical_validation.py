"""Bounded, deterministic checks for the subset of quiz math we can prove.

This is deliberately a small expression grammar, not a general computer algebra
system. Unknown notation is *unverified*, never silently certified.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from app.models.domain import QuizQuestion


VALIDATOR_VERSION = "arithmetic-linear-v1"
MAX_EXPRESSION_LENGTH = 96
MAX_NODES = 40
MAX_BITS = 256


@dataclass(frozen=True)
class MathAudit:
    status: Literal["verified", "unverified", "rejected"]
    reason: str


class _Unsupported(ValueError):
    pass


class _Invalid(ValueError):
    pass


def _bounded(value: Fraction) -> Fraction:
    if value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        raise _Unsupported("expression exceeds arithmetic limits")
    return value


def _normalize(expression: str) -> str:
    expression = expression.strip().replace("−", "-").replace("–", "-")
    expression = expression.replace("×", "*").replace("·", "*").replace("÷", "/")
    expression = expression.replace(r"\times", "*").replace(r"\cdot", "*").replace(r"\div", "/")
    expression = expression.replace("²", "^2").replace("³", "^3").replace("^", "**")
    expression = re.sub(r"(?<=\d),(?=\d)", ".", expression)
    expression = re.sub(r"\\frac\s*\{(\d{1,10})\}\s*\{(\d{1,10})\}", r"(\1/\2)", expression)
    return expression


def _evaluate(expression: str, variable: str | None = None) -> tuple[Fraction, Fraction]:
    """Return (coefficient of variable, constant), rejecting nonlinear input."""
    expr = _normalize(expression)
    if len(expr) > MAX_EXPRESSION_LENGTH or re.search(r"\d{13,}", expr):
        raise _Unsupported("expression too large")
    if variable:
        expr = re.sub(rf"(?<=\d)\s*(?={re.escape(variable)}\b)", "*", expr)
    if re.search(r"[^\d\s.()+\-*/a-zA-Z]", expr):
        raise _Unsupported("unsupported mathematical notation")
    try:
        tree = ast.parse(expr, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise _Unsupported("unsupported expression syntax") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise _Unsupported("expression too complex")

    def visit(node: ast.AST) -> tuple[Fraction, Fraction]:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            # The source literal is read as text below to avoid float rounding.
            value = ast.get_source_segment(expr, node)
            if value is None:
                raise _Unsupported("missing numeric literal")
            return Fraction(0), _bounded(Fraction(value))
        if isinstance(node, ast.Name) and variable and node.id == variable:
            return Fraction(1), Fraction(0)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            a, b = visit(node.operand)
            return (-a, -b) if isinstance(node.op, ast.USub) else (a, b)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            a, b = visit(node.left)
            c, d = visit(node.right)
            if isinstance(node.op, ast.Add):
                pair = a + c, b + d
            elif isinstance(node.op, ast.Sub):
                pair = a - c, b - d
            elif isinstance(node.op, ast.Mult):
                if a and c:
                    raise _Unsupported("nonlinear expression")
                pair = a * d + c * b, b * d
            elif isinstance(node.op, ast.Div):
                if c:
                    raise _Unsupported("variable in denominator")
                if not d:
                    raise _Invalid("division by zero")
                pair = a / d, b / d
            else:
                if c or d.denominator != 1 or d < 0 or d > 6 or a:
                    raise _Unsupported("unsupported exponent")
                pair = Fraction(0), b ** int(d)
            return _bounded(pair[0]), _bounded(pair[1])
        raise _Unsupported("unsupported expression element")

    return visit(tree)


def _scalar(expression: str) -> Fraction:
    coefficient, constant = _evaluate(expression)
    if coefficient:
        raise _Unsupported("variable in numeric answer")
    return constant


def _answer(choice: str) -> Fraction | None:
    choice = choice.strip()
    # Common LaTeX wrappers and explicit 'x = 6' response notation.
    choice = re.sub(r"^\\\((.*)\\\)$", r"\1", choice)
    choice = re.sub(r"^\$([^$]+)\$$", r"\1", choice)
    choice = re.sub(r"^[a-zA-Z]\s*=\s*", "", choice)
    if choice.endswith("%"):
        try:
            return _bounded(_scalar(choice[:-1]) / 100)
        except (_Unsupported, _Invalid, ZeroDivisionError):
            return None
    try:
        return _scalar(choice)
    except (_Unsupported, _Invalid, ZeroDivisionError):
        return None


def _expected(prompt: str) -> Fraction | None:
    content = prompt.strip().rstrip("?!. ").strip()
    percentage = re.fullmatch(
        r"(?:quanto\s+é|qual\s+é|what\s+is|calculate|calcule)\s+"
        r"(\d+(?:[.,]\d+)?)\s*%\s*(?:de|of)\s*(\d+(?:[.,]\d+)?)",
        content, flags=re.IGNORECASE,
    )
    if percentage:
        return _bounded(_scalar(percentage[1]) * _scalar(percentage[2]) / 100)

    equation = re.fullmatch(
        r"(?:se|if)\s+(.+?)\s*,\s*(?:qual\s+é|qual\s+e|what\s+is)\s+"
        r"(?:o\s+valor\s+de|the\s+value\s+of)\s+([a-zA-Z])",
        content, flags=re.IGNORECASE,
    )
    if equation:
        candidate, variable = equation[1], equation[2]
        if candidate.count("=") != 1:
            raise _Unsupported("unsupported equation")
        left, right = candidate.split("=", 1)
        return _solve(left, right, variable)

    simple = re.fullmatch(
        r"(?:quanto\s+é|qual\s+é\s+o\s+resultado\s+de|"
        r"qual\s+o\s+resultado\s+de|calcule|compute|calculate|"
        r"what\s+is|evaluate|simplifique|simplify|resolva|solve)\s+(.+)",
        content, flags=re.IGNORECASE,
    )
    if not simple:
        return None
    expression = simple[1].strip()
    if "=" in expression and expression.count("=") == 1:
        left, right = expression.split("=", 1)
        variables = set(re.findall(r"[a-zA-Z]", _normalize(expression)))
        if len(variables) != 1:
            raise _Unsupported("equation has unsupported variables")
        return _solve(left, right, variables.pop())
    try:
        return _scalar(expression)
    except _Unsupported:
        return None


def _solve(left: str, right: str, variable: str) -> Fraction:
    a, b = _evaluate(left, variable)
    c, d = _evaluate(right, variable)
    if a == c:
        raise _Invalid("equation has no unique solution")
    return _bounded((d - b) / (a - c))


def _explanation_conflict(question: QuizQuestion, expected: Fraction | None) -> bool:
    # Inspect explicit, scalar equalities only. No attempt to parse prose.
    explanation = _normalize(question.explanation)
    if len(explanation) > 2000:
        return False
    # Percent-of statements are complete expressions. Without this check the
    # scalar regexp would mistake the trailing '150 = 30' in '20% de 150 = 30'
    # for an independent equality and falsely reject a correct explanation.
    percentage_equality = re.compile(
        r"(?<![\w])([\d]+(?:\.\d+)?)\s*%\s*(?:de|of)\s*"
        r"([\d]+(?:\.\d+)?)\s*=\s*(-?\d+(?:\.\d+)?)\b",
        flags=re.IGNORECASE,
    )
    for match in percentage_equality.finditer(explanation):
        try:
            if _scalar(match[1]) * _scalar(match[2]) / 100 != _scalar(match[3]):
                return True
        except (_Unsupported, _Invalid, ZeroDivisionError):
            continue
    for match in re.finditer(r"(?<![\w])([\d][\d\s.+*/()\-]{0,60})\s*=\s*(-?\d+(?:\.\d+)?)\b", explanation):
        prefix = explanation[:match.start()].rstrip()
        # The numeric tail of '2x + 3 = 11' or 'x/3 = 2' is not a standalone
        # equality. Require the whole left side to be scalar before judging it.
        if prefix.endswith(("+", "-", "*", "/", "^", "(")):
            continue
        if re.search(r"\d+(?:\.\d+)?\s*%\s*(?:de|of)\s*$", prefix, flags=re.IGNORECASE):
            continue
        try:
            if _scalar(match[1]) != _scalar(match[2]):
                return True
        except (_Unsupported, _Invalid, ZeroDivisionError):
            continue
    if expected is not None:
        for match in re.finditer(r"(?<![\w])([a-zA-Z])\s*=\s*(-?\d+(?:\.\d+)?)\b", explanation):
            if re.search(rf"(?<![a-zA-Z]){re.escape(match[1])}(?![a-zA-Z])", question.prompt):
                if _scalar(match[2]) != expected:
                    return True
    return False


def audit_math_question(question: QuizQuestion) -> MathAudit:
    """Reject proven errors; certify only a scalar question with four parsed choices."""
    try:
        expected = _expected(question.prompt)
        values = [_answer(choice) for choice in question.choices]
        for i, value in enumerate(values):
            if value is not None and value in values[:i]:
                return MathAudit("rejected", "mathematically equivalent answer choices")
        if _explanation_conflict(question, expected):
            return MathAudit("rejected", "contradictory mathematical explanation")
        if expected is None:
            return MathAudit("unverified", "question is outside the supported deterministic math grammar")
        marked = values[question.correct_choice_index]
        if marked is not None and marked != expected:
            return MathAudit("rejected", "marked answer conflicts with independently calculated result")
        matches = [i for i, value in enumerate(values) if value == expected]
        if len(matches) > 1:
            return MathAudit("rejected", "multiple mathematically correct choices")
        if len(matches) == 0 and all(value is not None for value in values):
            return MathAudit("rejected", "no mathematically correct choice")
        if len(matches) == 1 and all(value is not None for value in values):
            return MathAudit("verified", "unique answer independently calculated")
        return MathAudit("unverified", "one or more answer choices use unsupported notation")
    except (_Invalid, ZeroDivisionError) as exc:
        return MathAudit("rejected", str(exc))
    except (_Unsupported, OverflowError, ValueError):
        return MathAudit("unverified", "question exceeds the supported math grammar or limits")
