# Agent Directives

## Strategy Development

When creating new trading strategies for OpenAlgo, **ALWAYS** refer to and follow the prompt stored in `docs/strategy_prompt.md`. This file contains the mandatory specifications, file structure, and risk management rules that must be adhered to.

The "OpenAlgo Strategy Development Prompt" mandates that:
- Strategies must inherit from `BaseStrategy`.
- Strategies must include specific enterprise risk parameters as module-level constants.
- Strategies must implement `generate_signal` as a module-level function for backtesting.
- Strategies must use `APIClient` from `trading_utils` and avoid `requests` library.
- Strategies must follow the specified file structure and logging practices.

This file serves as the definitive guide for all strategy development tasks. Please read `docs/strategy_prompt.md` before writing any new strategy code.
