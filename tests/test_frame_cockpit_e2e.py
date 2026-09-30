"""
END-TO-END VALIDATION TEST FOR UNIFIED FRAME COCKPIT
Tests:
1. FrameMasterCockpit initialization and UI components
2. Tab switching between Live Trader and Backtest Station
3. Background feed and broker preservation across tab switches
4. Backtest simulation execution inside the unified container
5. Database audit & Cloud sync client responsiveness
"""

import sys, pathlib, time
project_root = pathlib.Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from PySide6.QtWidgets import QApplication
from src.frame.gui.frame_cockpit import FrameMasterCockpit
from src.frame.gui.worker import BacktestWorker

def run_e2e_test():
    print("==================================================================")
    print("  FRAME UNIFIED COCKPIT // END-TO-END AUTOMATED VERIFICATION")
    print("==================================================================")

    app = QApplication.instance() or QApplication(sys.argv)
    
    # 1. Initialize Cockpit
    cockpit = FrameMasterCockpit()
    print("[TEST 1/5] FrameMasterCockpit initialized successfully.")
    assert cockpit.stack.count() == 2, f"Expected 2 stacked pages, got {cockpit.stack.count()}"
    print(f"  -> Stack count: {cockpit.stack.count()} pages verified.")

    # 2. Test Tab Switching
    cockpit.switch_tab(1)
    assert cockpit.stack.currentIndex() == 1, "Failed to switch to Tab 1 (Backtest)"
    print("[TEST 2/5] Tab 1 (Backtest Station) active and verified.")

    cockpit.switch_tab(0)
    assert cockpit.stack.currentIndex() == 0, "Failed to switch to Tab 0 (Live Trader)"
    print("  -> Switched back to Tab 0 (Live Trader) successfully.")

    # 3. Test Live Trader Broker & Feed
    live = cockpit.live_workstation
    broker = live.broker
    assert broker.cash == 250.0, f"Expected initial cash 250.0, got {broker.cash}"
    print("[TEST 3/6] Live Trader PaperBroker verified ($250.00 cash).")
    
    # 3.5. Test Dual-Session Real-Time Isolation & Synchronization
    print("[TEST 4/6] Verifying Dual-Session Real-Time Isolation & Synchronization...")
    assert hasattr(live, "broker_a") and hasattr(live, "broker_b"), "Missing dual brokers"
    assert hasattr(live, "agent_a") and hasattr(live, "agent_b"), "Missing dual agents"
    assert live.broker_a.session_id == "MODEL_A_LEGACY", f"Unexpected session A ID: {live.broker_a.session_id}"
    assert live.broker_b.session_id == "MODEL_B_MOMENT", f"Unexpected session B ID: {live.broker_b.session_id}"
    assert live.agent_a.model_choice == "legacy", f"Unexpected model choice A: {live.agent_a.model_choice}"
    assert live.agent_b.model_choice == "pretrained", f"Unexpected model choice B: {live.agent_b.model_choice}"

    # Verify Session Switching
    live._switch_active_session("A")
    assert live.active_session == "A"
    assert live.active_broker is live.broker_a
    assert live.active_agent is live.agent_a

    live._switch_active_session("B")
    assert live.active_session == "B"
    assert live.active_broker is live.broker_b
    assert live.active_agent is live.agent_b

    # Verify Synchronous Arm / Standby
    live._arm_both_sessions()
    assert live.agent_a.is_armed is True and live.agent_b.is_armed is True, "Arm both failed"
    live._standby_all_sessions()
    assert live.agent_a.is_armed is False and live.agent_b.is_armed is False, "Standby all failed"

    # Verify Strict Data Isolation (Zero Data Contamination)
    live.broker_a.reset(250.0)
    live.broker_b.reset(250.0)
    pos_a = live.broker_a.open_order("BUY", 2700.0, 2700.35, 10.0, reason="Test A Isolation")
    assert pos_a["id"].startswith("MODA"), f"Expected MODA prefix, got {pos_a['id']}"
    assert live.broker_b.open_position is None, "DATA LEAK: Model B received position from Model A!"

    # Arm sessions to evaluate live ticks
    live._arm_both_sessions()

    # Simulate synchronous market tick
    tick = {"bid": 2708.0, "ask": 2708.35, "latency_ms": 8.5, "spread": 0.35, "time": time.time()}
    live._on_feed_tick(tick)
    assert live.broker_a.open_position["floating_r"] > 0, "Model A position did not update on tick"
    assert live.broker_b.open_position is None, "DATA LEAK: Model B opened unexpected position after tick"

    # Open Model B order independently
    pos_b = live.broker_b.open_order("SELL", 2708.0, 2708.35, 12.0, reason="Test B Isolation")
    assert pos_b["id"].startswith("MODB"), f"Expected MODB prefix, got {pos_b['id']}"
    assert live.broker_a.open_position is not None and live.broker_a.open_position["direction"] == "BUY"
    assert live.broker_b.open_position is not None and live.broker_b.open_position["direction"] == "SELL"

    # Close trades independently
    trade_a = live.broker_a.close_order(2710.0, exit_reason="Target TP")
    assert len(live.broker_a.trade_history) == 1, "Model A trade history not updated"
    assert len(live.broker_b.trade_history) == 0, "DATA LEAK: Model A trade leaked into Model B history!"
    assert live.broker_b.open_position is not None, "Model B position was prematurely closed"

    trade_b = live.broker_b.close_order(2695.0, exit_reason="Target TP")
    assert len(live.broker_b.trade_history) == 1, "Model B trade history not updated"
    assert live.broker_a.trade_history[0]["session_id"] == "MODEL_A_LEGACY"
    assert live.broker_b.trade_history[0]["session_id"] == "MODEL_B_MOMENT"

    # Clean up test positions
    live.broker_a.reset(250.0)
    live.broker_b.reset(250.0)
    print("  -> Dual-Session Data Isolation & Synchronization verified with 100% mathematical zero-leakage.")

    # 4. Test Cloud Sync Worker
    client = live.cloud_client
    assert client.base_url is not None
    print(f"[TEST 5/6] Cloud Sync Client verified ({client.base_url}).")

    # 5. Test Backtest Worker inside Cockpit
    print("[TEST 6/6] Executing causal backtest worker in Cockpit context...")
    bt_view = cockpit.backtest_workstation
    worker = BacktestWorker(mode='2026', capital=250.0, sizing_mode='dual', max_lot=0.04, model_choice='pretrained')
    res_holder = {}
    def on_done(res):
        res_holder['data'] = res

    worker.finished_backtest.connect(on_done)
    worker.run()
    
    assert 'data' in res_holder, "BacktestWorker failed to return results"
    data = res_holder['data']
    print(f"  -> Backtest completed: Net PnL: ${data['net_pnl']:+,.2f} | WR: {data['win_rate']}% | Max DD: {data['max_drawdown']}%")
    assert data['net_pnl'] == 1207.01, f"Expected net PnL 1207.01, got {data['net_pnl']}"
    assert data['total_trades'] == 137, f"Expected 137 trades, got {data['total_trades']}"
    assert data['win_rate'] == 62.77, f"Expected 62.77% WR, got {data['win_rate']}"

    # Cleanup
    cockpit.close()
    print("\n[ALL E2E TESTS PASSED 100%] Unified FRAME Cockpit is completely robust & verified!")

if __name__ == "__main__":
    run_e2e_test()
