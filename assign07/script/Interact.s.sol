// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script, console} from "forge-std/Script.sol";
import {Escrow} from "../src/Escrow.sol";

contract Interact is Script {
    string constant MNEMONIC = "test test test test test test test test test test test junk";

    function run() external {
        uint256 deployerPk = vm.deriveKey(MNEMONIC, 0);
        uint256 buyerPk    = vm.deriveKey(MNEMONIC, 1);
        uint256 sellerPk   = vm.deriveKey(MNEMONIC, 2);
        uint256 arbiterPk  = vm.deriveKey(MNEMONIC, 3);

        // 1. deploy
        vm.startBroadcast(deployerPk);
        Escrow e = new Escrow(vm.addr(buyerPk), vm.addr(sellerPk), vm.addr(arbiterPk));
        vm.stopBroadcast();
        console.log("Escrow deployed at:", address(e));

        // 2. buyer funds and releases
        vm.startBroadcast(buyerPk);
        e.fund{value: 1 ether}();
        e.release();
        vm.stopBroadcast();

        // 3. seller pulls payment
        vm.startBroadcast(sellerPk);
        e.withdraw();
        vm.stopBroadcast();

        console.log("Final state (2 = Released):", uint256(e.state()));
        console.log("Escrow balance:", address(e).balance);
        console.log("Liabilities:", e.liabilities());
    }
}