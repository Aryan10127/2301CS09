// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title Escrow (buyer / seller / arbiter)
/// @notice Educational contract. See SPEC.md for the state machine.
contract Escrow {
    enum State { Created, Funded, Released, Disputed, ResolvedToBuyer, ResolvedToSeller, Cancelled }

    error ZeroAddress();
    error RoleOverlap();
    error NotAuthorized();
    error InvalidState(State current);
    error ZeroAmount();
    error NothingToWithdraw();
    error TransferFailed();
    error Reentrancy();

    event Funded(address indexed buyer, uint256 amount);
    event PaymentReleased(address indexed seller, uint256 amount);
    event DisputeRaised(address indexed by);
    event DisputeResolved(bool indexed toBuyer, address indexed beneficiary, uint256 amount);
    event CancelApproved(address indexed by);
    event EscrowCancelled();
    event Withdrawn(address indexed to, uint256 amount);

    address public immutable buyer;
    address public immutable seller;
    address public immutable arbiter;

    State public state;
    uint256 public amount;        // amount deposited by the buyer
    uint256 public pendingTotal;  // sum of all unclaimed withdrawals
    mapping(address => uint256) public pending;

    bool public buyerApprovedCancel;
    bool public sellerApprovedCancel;

    uint256 private _lock = 1;

    modifier nonReentrant() {
        if (_lock != 1) revert Reentrancy();
        _lock = 2;
        _;
        _lock = 1;
    }

    constructor(address _buyer, address _seller, address _arbiter) {
        if (_buyer == address(0) || _seller == address(0) || _arbiter == address(0)) revert ZeroAddress();
        if (_buyer == _seller || _buyer == _arbiter || _seller == _arbiter) revert RoleOverlap();
        buyer = _buyer;
        seller = _seller;
        arbiter = _arbiter;
        // state defaults to Created
    }

    // ---------------- state transitions ----------------

    /// Created -> Funded
    function fund() external payable {
        if (msg.sender != buyer) revert NotAuthorized();
        if (state != State.Created) revert InvalidState(state);
        if (msg.value == 0) revert ZeroAmount();

        state = State.Funded;
        amount = msg.value;
        emit Funded(msg.sender, msg.value);
    }

    /// Funded -> Released (buyer only). Seller must then withdraw().
    function release() external {
        if (msg.sender != buyer) revert NotAuthorized();
        if (state != State.Funded) revert InvalidState(state);

        state = State.Released;
        _credit(seller, amount);
        emit PaymentReleased(seller, amount);
    }

    /// Funded -> Disputed (buyer or seller)
    function raiseDispute() external {
        if (msg.sender != buyer && msg.sender != seller) revert NotAuthorized();
        if (state != State.Funded) revert InvalidState(state);

        state = State.Disputed;
        emit DisputeRaised(msg.sender);
    }

    /// Disputed -> ResolvedToBuyer | ResolvedToSeller (arbiter only)
    function resolve(bool toBuyer) external {
        if (msg.sender != arbiter) revert NotAuthorized();
        if (state != State.Disputed) revert InvalidState(state);

        address beneficiary;
        if (toBuyer) {
            state = State.ResolvedToBuyer;
            beneficiary = buyer;
        } else {
            state = State.ResolvedToSeller;
            beneficiary = seller;
        }
        _credit(beneficiary, amount);
        emit DisputeResolved(toBuyer, beneficiary, amount);
    }

    /// Created -> Cancelled once BOTH buyer and seller approve.
    function approveCancel() external {
        if (msg.sender != buyer && msg.sender != seller) revert NotAuthorized();
        if (state != State.Created) revert InvalidState(state);

        if (msg.sender == buyer) buyerApprovedCancel = true;
        else sellerApprovedCancel = true;
        emit CancelApproved(msg.sender);

        if (buyerApprovedCancel && sellerApprovedCancel) {
            state = State.Cancelled;
            emit EscrowCancelled();
        }
    }

    // ---------------- pull payment ----------------

    function withdraw() external nonReentrant {
        uint256 v = pending[msg.sender];
        if (v == 0) revert NothingToWithdraw();

        // effects before interaction
        pending[msg.sender] = 0;
        pendingTotal -= v;
        emit Withdrawn(msg.sender, v);

        (bool ok, ) = msg.sender.call{value: v}("");
        if (!ok) revert TransferFailed();
    }

    // ---------------- views ----------------

    /// Funds the contract is obliged to hold: escrowed amount (if live) + unclaimed withdrawals.
    function liabilities() public view returns (uint256) {
        uint256 held = (state == State.Funded || state == State.Disputed) ? amount : 0;
        return held + pendingTotal;
    }

    function _credit(address to, uint256 a) internal {
        pending[to] += a;
        pendingTotal += a;
    }
}