// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {Escrow} from "../src/Escrow.sol";

contract ReentrantSeller {
    Escrow public e;
    bool public reentryBlocked;

    function setEscrow(Escrow _e) external { e = _e; }
    function attack() external { e.withdraw(); }

    receive() external payable {
        try e.withdraw() {} catch { reentryBlocked = true; }
    }
}

contract EscrowTest is Test {
    Escrow e;
    address buyer = makeAddr("buyer");
    address seller = makeAddr("seller");
    address arbiter = makeAddr("arbiter");
    address stranger = makeAddr("stranger");
    uint256 constant AMT = 1 ether;

    function setUp() public {
        e = new Escrow(buyer, seller, arbiter);
        vm.deal(buyer, 100 ether);
    }

    // ---------- helpers ----------
    function _fund() internal { vm.prank(buyer); e.fund{value: AMT}(); }
    function _dispute() internal { _fund(); vm.prank(seller); e.raiseDispute(); }
    function _solvent() internal view { assertEq(address(e).balance, e.liabilities(), "balance != liabilities"); }
    function _badState(Escrow.State s) internal pure returns (bytes memory) {
        return abi.encodeWithSelector(Escrow.InvalidState.selector, s);
    }

    // ---------- constructor ----------
    function test_Constructor_RejectsZeroAddresses() public {
        vm.expectRevert(Escrow.ZeroAddress.selector);
        new Escrow(address(0), seller, arbiter);
        vm.expectRevert(Escrow.ZeroAddress.selector);
        new Escrow(buyer, address(0), arbiter);
        vm.expectRevert(Escrow.ZeroAddress.selector);
        new Escrow(buyer, seller, address(0));
    }

    function test_Constructor_RejectsRoleOverlap() public {
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(buyer, buyer, arbiter);
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(buyer, seller, buyer);
        vm.expectRevert(Escrow.RoleOverlap.selector);
        new Escrow(buyer, seller, seller);
    }

    // ---------- fund ----------
    function test_Fund_Succeeds() public {
        vm.expectEmit(true, false, false, true);
        emit Escrow.Funded(buyer, AMT);
        _fund();
        assertEq(uint8(e.state()), uint8(Escrow.State.Funded));
        assertEq(e.amount(), AMT);
        _solvent();
    }

    function test_Fund_OnlyBuyer() public {
        vm.deal(stranger, 1 ether);
        vm.prank(stranger);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.fund{value: AMT}();
    }

    function test_Fund_ZeroValueReverts() public {
        vm.prank(buyer);
        vm.expectRevert(Escrow.ZeroAmount.selector);
        e.fund{value: 0}();
    }

    function test_Fund_Twice_Reverts() public {
        _fund();
        vm.prank(buyer);
        vm.expectRevert(_badState(Escrow.State.Funded));
        e.fund{value: AMT}();
        _solvent();
    }

    function test_DirectEthTransfer_Reverts() public {
        vm.deal(stranger, 1 ether);
        vm.prank(stranger);
        (bool ok, ) = address(e).call{value: 1 ether}("");
        assertFalse(ok);
    }

    // ---------- release ----------
    function test_Release_Succeeds_ThenSellerWithdraws() public {
        _fund();
        vm.expectEmit(true, false, false, true);
        emit Escrow.PaymentReleased(seller, AMT);
        vm.prank(buyer);
        e.release();
        assertEq(uint8(e.state()), uint8(Escrow.State.Released));
        assertEq(e.pending(seller), AMT);
        _solvent();

        vm.expectEmit(true, false, false, true);
        emit Escrow.Withdrawn(seller, AMT);
        vm.prank(seller);
        e.withdraw();
        assertEq(seller.balance, AMT);
        assertEq(address(e).balance, 0);
        _solvent();
    }

    function test_Release_OnlyBuyer() public {
        _fund();
        vm.prank(seller);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.release();
    }

    function test_Release_FromCreated_Reverts() public {
        vm.prank(buyer);
        vm.expectRevert(_badState(Escrow.State.Created));
        e.release();
    }

    // ---------- dispute ----------
    function test_Dispute_ByBuyer() public {
        _fund();
        vm.expectEmit(true, false, false, false);
        emit Escrow.DisputeRaised(buyer);
        vm.prank(buyer);
        e.raiseDispute();
        assertEq(uint8(e.state()), uint8(Escrow.State.Disputed));
        _solvent();
    }

    function test_Dispute_BySeller() public {
        _dispute();
        assertEq(uint8(e.state()), uint8(Escrow.State.Disputed));
    }

    function test_Dispute_StrangerAndArbiterReverts() public {
        _fund();
        vm.prank(stranger);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.raiseDispute();
        vm.prank(arbiter);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.raiseDispute();
    }

    function test_Dispute_FromCreated_Reverts() public {
        vm.prank(buyer);
        vm.expectRevert(_badState(Escrow.State.Created));
        e.raiseDispute();
    }

    // ---------- resolve ----------
    function test_Resolve_ToBuyer() public {
        _dispute();
        vm.expectEmit(true, true, false, true);
        emit Escrow.DisputeResolved(true, buyer, AMT);
        vm.prank(arbiter);
        e.resolve(true);
        assertEq(uint8(e.state()), uint8(Escrow.State.ResolvedToBuyer));
        assertEq(e.pending(buyer), AMT);
        _solvent();

        uint256 before = buyer.balance;
        vm.prank(buyer);
        e.withdraw();
        assertEq(buyer.balance, before + AMT);
        _solvent();
    }

    function test_Resolve_ToSeller() public {
        _dispute();
        vm.prank(arbiter);
        e.resolve(false);
        assertEq(uint8(e.state()), uint8(Escrow.State.ResolvedToSeller));
        vm.prank(seller);
        e.withdraw();
        assertEq(seller.balance, AMT);
        _solvent();
    }

    function test_Resolve_OnlyArbiter() public {
        _dispute();
        vm.prank(buyer);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.resolve(true);
        vm.prank(seller);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.resolve(false);
    }

    function test_Resolve_FromFunded_Reverts() public {
        _fund();
        vm.prank(arbiter);
        vm.expectRevert(_badState(Escrow.State.Funded));
        e.resolve(true);
    }

    // ---------- cancel ----------
    function test_Cancel_RequiresBothParties() public {
        vm.prank(buyer);
        e.approveCancel();
        assertEq(uint8(e.state()), uint8(Escrow.State.Created));

        vm.expectEmit(false, false, false, false);
        emit Escrow.EscrowCancelled();
        vm.prank(seller);
        e.approveCancel();
        assertEq(uint8(e.state()), uint8(Escrow.State.Cancelled));
    }

    function test_Cancel_StrangerReverts() public {
        vm.prank(stranger);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.approveCancel();
        vm.prank(arbiter);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.approveCancel();
    }

    function test_Cancel_AfterFunded_Reverts() public {
        _fund();
        vm.prank(buyer);
        vm.expectRevert(_badState(Escrow.State.Funded));
        e.approveCancel();
    }

    function test_Fund_AfterCancel_Reverts() public {
        vm.prank(buyer); e.approveCancel();
        vm.prank(seller); e.approveCancel();
        vm.prank(buyer);
        vm.expectRevert(_badState(Escrow.State.Cancelled));
        e.fund{value: AMT}();
    }

    // ---------- terminal states: no further transitions ----------
    function _assertAllTransitionsRevert() internal {
        vm.startPrank(buyer);
        vm.expectRevert(); e.fund{value: AMT}();
        vm.expectRevert(); e.release();
        vm.expectRevert(); e.raiseDispute();
        vm.expectRevert(); e.approveCancel();
        vm.stopPrank();
        vm.startPrank(seller);
        vm.expectRevert(); e.raiseDispute();
        vm.expectRevert(); e.approveCancel();
        vm.stopPrank();
        vm.prank(arbiter);
        vm.expectRevert(); e.resolve(true);
    }

    function test_Terminal_Released() public {
        _fund(); vm.prank(buyer); e.release();
        _assertAllTransitionsRevert();
    }

    function test_Terminal_ResolvedToBuyer() public {
        _dispute(); vm.prank(arbiter); e.resolve(true);
        _assertAllTransitionsRevert();
    }

    function test_Terminal_ResolvedToSeller() public {
        _dispute(); vm.prank(arbiter); e.resolve(false);
        _assertAllTransitionsRevert();
    }

    function test_Terminal_Cancelled() public {
        vm.prank(buyer); e.approveCancel();
        vm.prank(seller); e.approveCancel();
        _assertAllTransitionsRevert();
    }

    // ---------- withdraw ----------
    function test_Withdraw_NothingReverts() public {
        vm.prank(stranger);
        vm.expectRevert(Escrow.NothingToWithdraw.selector);
        e.withdraw();
    }

    function test_Withdraw_CannotPayTwice() public {
        _fund(); vm.prank(buyer); e.release();
        vm.startPrank(seller);
        e.withdraw();
        vm.expectRevert(Escrow.NothingToWithdraw.selector);
        e.withdraw();
        vm.stopPrank();
        assertEq(seller.balance, AMT);
    }

    function test_Withdraw_ReentrancyBlocked() public {
        ReentrantSeller atk = new ReentrantSeller();
        Escrow e2 = new Escrow(buyer, address(atk), arbiter);
        atk.setEscrow(e2);

        vm.startPrank(buyer);
        e2.fund{value: AMT}();
        e2.release();
        vm.stopPrank();

        atk.attack();
        assertTrue(atk.reentryBlocked());
        assertEq(address(atk).balance, AMT);   // paid exactly once
        assertEq(address(e2).balance, 0);
    }

    // ---------- fuzz ----------
    function testFuzz_Amount_ReleaseFlow(uint96 raw) public {
        uint256 a = bound(raw, 1, type(uint96).max);
        vm.deal(buyer, a);
        vm.prank(buyer); e.fund{value: a}();
        _solvent();
        vm.prank(buyer); e.release();
        _solvent();
        vm.prank(seller); e.withdraw();
        assertEq(seller.balance, a);
        assertEq(address(e).balance, 0);
        _solvent();
    }

    function testFuzz_Amount_DisputeFlow(uint96 raw, bool toBuyer) public {
        uint256 a = bound(raw, 1, type(uint96).max);
        vm.deal(buyer, a);
        vm.prank(buyer); e.fund{value: a}();
        vm.prank(seller); e.raiseDispute();
        vm.prank(arbiter); e.resolve(toBuyer);
        _solvent();
        address winner = toBuyer ? buyer : seller;
        uint256 before = winner.balance;
        vm.prank(winner); e.withdraw();
        assertEq(winner.balance, before + a);
        assertEq(address(e).balance, 0);
    }

    function testFuzz_Caller_CannotRelease(address caller) public {
        vm.assume(caller != buyer);
        _fund();
        vm.prank(caller);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.release();
        _solvent();
    }

    function testFuzz_Caller_CannotResolve(address caller) public {
        vm.assume(caller != arbiter);
        _dispute();
        vm.prank(caller);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.resolve(true);
        _solvent();
    }

    function testFuzz_Caller_CannotFund(address caller) public {
        vm.assume(caller != buyer);
        vm.deal(caller, 1 ether);
        vm.prank(caller);
        vm.expectRevert(Escrow.NotAuthorized.selector);
        e.fund{value: 1 ether}();
    }
}