# -*- coding: utf-8 -*-
# ------------------------------------------------------------------------------
#
#   Copyright 2024 Valory AG
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
# ------------------------------------------------------------------------------

"""This package contains round behaviours of LearningAbciApp."""

from abc import ABC
from typing import Generator, Set, Type, cast, Optional, Dict, Any, List

from packages.valory.skills.abstract_round_abci.base import AbstractRound
from packages.valory.skills.abstract_round_abci.behaviours import (
    AbstractRoundBehaviour,
    BaseBehaviour,
)
from packages.valory.skills.learning_abci.models import Params, SharedState
from packages.valory.skills.learning_abci.payloads import (
    APICheckPayload,
    DecisionMakingPayload,
    TxPreparationPayload,
)
from packages.valory.skills.learning_abci.rounds import (
    APICheckRound,
    DecisionMakingRound,
    Event,
    LearningAbciApp,
    SynchronizedData,
    TxPreparationRound,
)
import json
from packages.valory.contracts.real_estate_solution.contract import (
    RealEstateSolutionContract,
)
from packages.valory.skills.abstract_round_abci.io_.store import SupportedFiletype
from packages.valory.protocols.contract_api import ContractApiMessage
from packages.valory.skills.transaction_settlement_abci.payload_tools import (
    hash_payload_to_hex,
)
from packages.valory.contracts.gnosis_safe.contract import (
    GnosisSafeContract,
    SafeOperation,
)
from packages.valory.contracts.erc20.contract import ERC20
from packages.valory.contracts.multisend.contract import (
    MultiSendContract,
    MultiSendOperation,
)
from hexbytes import HexBytes

HTTP_OK = 200
GNOSIS_CHAIN_ID = "gnosis"
TX_DATA = b"0x"
SAFE_GAS = 0
VALUE_KEY = "value"
TO_ADDRESS_KEY = "to_address"
MULTISEND_ADDRESS = "0xA238CBeb142c10Ef7Ad8442C6D1f9E89e07e7761"


class LearningBaseBehaviour(BaseBehaviour, ABC):  # pylint: disable=too-many-ancestors
    """Base behaviour for the learning_abci skill."""

    @property
    def synchronized_data(self) -> SynchronizedData:
        """Return the synchronized data."""
        return cast(SynchronizedData, super().synchronized_data)

    @property
    def params(self) -> Params:
        """Return the params."""
        return cast(Params, super().params)

    @property
    def local_state(self) -> SharedState:
        """Return the state."""
        return cast(SharedState, self.context.state)


class APICheckBehaviour(LearningBaseBehaviour):  # pylint: disable=too-many-ancestors
    """APICheckBehaviour"""

    matching_round: Type[AbstractRound] = APICheckRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            price = yield from self.get_price()

            contract_response = yield from self.get_contract_api_response(
                performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
                contract_id=str(RealEstateSolutionContract.contract_id),
                contract_callable="get_properties_for_sale",
                contract_address=self.params.real_estate_contract_address,
                chain_id=GNOSIS_CHAIN_ID,
            )
            self.context.logger.info(
                f"These are the properties for sale: {contract_response}"
            )

            properties_for_sale = contract_response.state.body["data"]
            ipfs_hash = yield from self.send_to_ipfs(
                "ListedProperties.json",
                {"Properties for sale: ": properties_for_sale},
                filetype=SupportedFiletype.JSON,
            )

            self.context.logger.info(f"The IPFS hash is : {ipfs_hash}")
            payload = APICheckPayload(sender=sender, price=price, ipfs_hash=ipfs_hash)

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_price(self):
        """Get token price from Coingecko"""
        response = yield from self.get_http_response(
            method="GET",
            url=self.params.coingecko_price_template,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-cg-demo-api-key": self.params.coingecko_api_key,
            },
        )
        if response.status_code != 200:
            self.context.logger.error(
                f"Error in fetch the price,Status_code{response.status_code}"
            )

        try:
            response_body = response.body
            response_data = json.loads(response_body)
            price = response_data["autonolas"]["usd"]
            self.context.logger.info(f"The price is {price}")
            return price
        except json.JSONDecodeError:
            self.context.logger.error("Could not parse the response body")
            return None


class DecisionMakingBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """DecisionMakingBehaviour"""

    matching_round: Type[AbstractRound] = DecisionMakingRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            sender = self.context.agent_address
            event, property_data = yield from self.make_transaction_decision()
            self.context.logger.info(f"The decision is : {event}")
            self.context.logger.info(f"Chooses bought property is : {property_data}")
            payload = DecisionMakingPayload(
                sender=sender,
                content=json.dumps(
                    {"event": event, "property_data": property_data}, sort_keys=True
                ),
            )

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def make_transaction_decision(self) -> Generator[None, None, str]:
        """
        Decide whether to buy the property if the price range is in buying zone
        """
        property_response_from_ipfs = yield from self.get_from_ipfs(
            self.synchronized_data.ipfs_hash, filetype=SupportedFiletype.JSON
        )
        self.context.logger.info(
            f"DATA RETRIEVED FROM IPFS {property_response_from_ipfs}"
        )

        properties_for_sale = property_response_from_ipfs["Properties for sale: "]
        # Log the buying range
        self.context.logger.info(f"Buying range: {self.params.buy_price_range}")
        for property in properties_for_sale:
            property_value = int(property[3])
            self.context.logger.info(f"Property value: {property_value}")
            if (
                self.params.buy_price_range[0]
                < property_value
                < self.params.buy_price_range[1]
            ):
                self.context.logger.info(
                    f"Deciding to BUY property with value: {property}"
                )
                return Event.TRANSACT.value, {
                    "property_id": property[0],
                    "property_value": property[3],
                }

        self.context.logger.info(
            "No properties within the buying range; deciding to HOLD"
        )
        return Event.DONE.value, {}


class TxPreparationBehaviour(
    LearningBaseBehaviour
):  # pylint: disable=too-many-ancestors
    """TxPreparationBehaviour"""

    ETHER_VALUE = 0

    matching_round: Type[AbstractRound] = TxPreparationRound

    def async_act(self) -> Generator:
        """Do the act, supporting asynchronous execution."""

        with self.context.benchmark_tool.measure(self.behaviour_id).local():
            update_real_estate_payload = yield from self.get_real_estate_update()

        with self.context.benchmark_tool.measure(self.behaviour_id).consensus():
            payload = TxPreparationPayload(
                self.context.agent_address, update_real_estate_payload
            )
            yield from self.send_a2a_transaction(payload)
            yield from self.wait_until_round_end()

        self.set_done()

    def get_real_estate_update(self) -> Generator[None, None, str]:
        """
        Check whether buy property txn needs to be made

        """
        self.context.logger.info(
            f"in Transction id: {self.synchronized_data.property_id}"
        )
        self.context.logger.info(
            f"in Transction value: {self.synchronized_data.property_value}"
        )
        self.context.logger.info("Transaction decision is Buy")
        batch_transaction = yield from self._build_approve_and_buy_txns()
        if batch_transaction is None:
            return "{}"
        
        multi_send_tx_data = yield from self._get_multisend_tx(batch_transaction)
        self.context.logger.info(f"MULTISEND TRANSACTIONS: {multi_send_tx_data}")
        if multi_send_tx_data is None:
            return "{}"
        return multi_send_tx_data

    def _build_buy_txn(self) -> Generator[None, None, Optional[bytes]]:

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(RealEstateSolutionContract.contract_id),
            contract_callable="get_buy_property_tx",
            contract_address=self.params.real_estate_contract_address,
            chain_id=GNOSIS_CHAIN_ID,
            id=self.synchronized_data.property_id,
        )

        self.context.logger.info(f"BUY TXN: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehaviour says: Couldn't get tx data for the txn. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        data_str = cast(str, response.state.body["data"])[2:]
        txn = bytes.fromhex(data_str)
        return txn

    def _build_approve_txn(self) -> Generator[None, None, Optional[bytes]]:
        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_STATE,  # type: ignore
            contract_id=str(ERC20.contract_id),
            contract_callable="build_approval_tx",
            contract_address=self.params.real_estate_token,
            spender=self.params.real_estate_contract_address,
            amount=self.synchronized_data.property_value,
        )

        self.context.logger.info(f"APPROVE TXN: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehaviour says: Couldn't get tx data for the txn. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        data_str = cast(str, response.state.body["data"])[2:]
        data = bytes.fromhex(data_str)
        return data

    def _build_approve_and_buy_txns(
        self,
    ) -> Generator[None, None, Optional[List[bytes]]]:
        transactions: List[bytes] = []

        approve_tx_data = yield from self._build_approve_txn()
        if approve_tx_data is None:
            return None
        transactions.append(approve_tx_data)

        buy_tx_data = yield from self._build_buy_txn()
        if buy_tx_data is None:
            return None
        transactions.append(buy_tx_data)

        return transactions

    def _get_safe_tx_hash(
        self, data: bytes, to_address: str, is_multisend: bool = False
    ) -> Generator[None, None, Optional[str]]:
        """
        Prepares and returns the safe tx hash.

        This hash will be signed later by the agents, and submitted to the safe contract.
        Note that this is the transaction that the safe will execute, with the provided data.

        :param data: the safe tx data. This is the data of the function being called, in this case `updateWeightGradually`.
        :return: the tx hash
        """
        contract_api_kwargs = {
            "performative": ContractApiMessage.Performative.GET_STATE,  # type: ignore
            "contract_address": self.synchronized_data.safe_contract_address,  # the safe contract address
            "contract_id": str(GnosisSafeContract.contract_id),
            "contract_callable": "get_raw_safe_transaction_hash",
            "to_address": to_address,
            "value": self.ETHER_VALUE,
            "data": data,
            "safe_tx_gas": SAFE_GAS,
            "chain_id": GNOSIS_CHAIN_ID,
            "operation": SafeOperation.DELEGATE_CALL.value
        }

        self.context.logger.info(f"contract_api_kwargs is: {contract_api_kwargs}")
        response = yield from self.get_contract_api_response(**contract_api_kwargs)
        self.context.logger.info(f"contract api response for safe_tx: {response}")

        if response.performative != ContractApiMessage.Performative.STATE:
            self.context.logger.error(
                f"TxPreparationBehaviour says: Couldn't get safe hash. "
                f"Expected response performative {ContractApiMessage.Performative.STATE.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response hash
        tx_hash = cast(str, response.state.body["tx_hash"])[2:]
        return tx_hash

    def _get_multisend_tx(
        self, txs: List[bytes]
    ) -> Generator[None, None, Optional[str]]:
        """Given a list of transactions, bundle them together in a single multisend tx."""
        multi_send_txs = []

        multi_send_approve_tx = self._to_multisend_format(
            txs[0], self.params.real_estate_token
        )
        self.context.logger.info(f"multi_send_approve_tx is: {multi_send_approve_tx}")
        multi_send_txs.append(multi_send_approve_tx)

        multi_send_buy_tx = self._to_multisend_format(
            txs[1], self.params.real_estate_contract_address
        )
        self.context.logger.info(f"multi_send_buy_tx is: {multi_send_buy_tx}")
        multi_send_txs.append(multi_send_buy_tx)

        response = yield from self.get_contract_api_response(
            performative=ContractApiMessage.Performative.GET_RAW_TRANSACTION,  # type: ignore
            contract_address=MULTISEND_ADDRESS,
            contract_id=str(MultiSendContract.contract_id),
            contract_callable="get_tx_data",
            multi_send_txs=multi_send_txs,
        )

        self.context.logger.info(f"PREPARED MULTISEND TXN:{response}")

        if response.performative != ContractApiMessage.Performative.RAW_TRANSACTION:
            self.context.logger.error(
                f"Couldn't compile the multisend tx. "
                f"Expected response performative {ContractApiMessage.Performative.RAW_TRANSACTION.value}, "  # type: ignore
                f"received {response.performative.value}."
            )
            return None

        # strip "0x" from the response
        multisend_data_str = cast(str, response.raw_transaction.body["data"])[2:]
        # self.context.logger.info("multisend_data_str is: %s", multisend_data_str)

        tx_data = bytes.fromhex(multisend_data_str)
        # self.context.logger.info(f"tx_data is: {tx_data}")
        tx_hash = yield from self._get_safe_tx_hash(
            tx_data, MULTISEND_ADDRESS, is_multisend=True
        )
        # self.context.logger.info(f"tx hash is {tx_hash}")

        if tx_hash is None:
            return None

        payload_data = hash_payload_to_hex(
            safe_tx_hash=tx_hash,
            ether_value=self.ETHER_VALUE,
            safe_tx_gas=SAFE_GAS,
            operation=SafeOperation.DELEGATE_CALL.value,
            to_address=MULTISEND_ADDRESS,
            data=tx_data,
        )
        return payload_data

    def _to_multisend_format(self, single_tx: bytes, to_address) -> Dict[str, Any]:
        """This method puts tx data from a single tx into the multisend format."""
        multisend_format = {
            "operation": MultiSendOperation.CALL,
            "to": to_address,
            "value": self.ETHER_VALUE,
            "data": HexBytes(single_tx),
        }
        return multisend_format


class LearningRoundBehaviour(AbstractRoundBehaviour):
    """LearningRoundBehaviour"""

    initial_behaviour_cls = APICheckBehaviour
    abci_app_cls = LearningAbciApp  # type: ignore
    behaviours: Set[Type[BaseBehaviour]] = [  # type: ignore
        APICheckBehaviour,
        DecisionMakingBehaviour,
        TxPreparationBehaviour,
    ]
