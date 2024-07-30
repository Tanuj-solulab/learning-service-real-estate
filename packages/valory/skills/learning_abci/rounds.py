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

"""This package contains the rounds of LearningAbciApp."""

from enum import Enum
from typing import Dict, FrozenSet, Optional, Set, Tuple, cast

from packages.valory.skills.abstract_round_abci.base import (
    AbciApp,
    AbciAppTransitionFunction,
    AppState,
    BaseSynchronizedData,
    CollectSameUntilThresholdRound,
    CollectionRound,
    DegenerateRound,
    DeserializedCollection,
    EventToTimeout,
    get_name,
)
from packages.valory.skills.learning_abci.payloads import (
    APICheckPayload,
    DecisionMakingPayload,
    TxPreparationPayload,
)
import json


class Event(Enum):
    """LearningAbciApp Events"""

    DONE = "done"
    ERROR = "error"
    TRANSACT = "transact"
    NO_MAJORITY = "no_majority"
    ROUND_TIMEOUT = "round_timeout"
    # HOLD = "hold"
    # BUY = "buy"


class SynchronizedData(BaseSynchronizedData):
    """
    Class to represent the synchronized data.

    This data is replicated by the tendermint application.
    """

    def _get_deserialized(self, key: str) -> DeserializedCollection:
        """Strictly get a collection and return it deserialized."""
        serialized = self.db.get_strict(key)
        return CollectionRound.deserialize_collection(serialized)

    @property
    def price(self) -> Optional[float]:
        """Get the token price."""
        return self.db.get("price", None)

    @property
    def participant_to_price_round(self) -> DeserializedCollection:
        """Get the participants to the price round."""
        return self._get_deserialized("participant_to_price_round")

    @property
    def most_voted_tx_hash(self) -> Optional[float]:
        """Get the token most_voted_tx_hash."""
        return self.db.get("most_voted_tx_hash", None)

    @property
    def participant_to_tx_round(self) -> DeserializedCollection:
        """Get the participants to the tx round."""
        return self._get_deserialized("participant_to_tx_round")

    @property
    def tx_submitter(self) -> str:
        """Get the round that submitted a tx to transaction_settlement_abci."""
        return str(self.db.get_strict("tx_submitter"))

    @property
    def ipfs_hash(self) -> Optional[str]:
        """Get the ipfs hash value."""
        return self.db.get("ipfs_hash", None)

    # @property
    # def property_data(self) -> Optional[Dict[str, any]]:
    #     """
    #     Get the property data.

    #     This assumes property_data is stored as a JSON string.
    #     """
    #     serialized_data = self.db.get("property_data", None)
    #     if serialized_data:
    #         try:
    #             return json.loads(serialized_data)
    #         except json.JSONDecodeError:
    #             self.context.logger.error("Failed to deserialize property_data from JSON.")
    #             return None
    #     return None

    @property
    def property_id(self) -> Optional[str]:
        """
        Get the property ID from property data.

        Assumes property_data is a JSON object with a 'property_id' key.
        """
        return self.db.get("property_id")

    @property
    def property_value(self) -> Optional[int]:
        """
        Get the property value from property data.

        Assumes property_data is a JSON object with a 'property_value' key.
        """
        return self.db.get("property_value")


class APICheckRound(CollectSameUntilThresholdRound):
    """APICheckRound"""

    payload_class = APICheckPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_price_round)
    selection_key = (
        get_name(SynchronizedData.price),
        get_name(SynchronizedData.ipfs_hash),
    )

    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class DecisionMakingRound(CollectSameUntilThresholdRound):
    """DecisionMakingRound"""

    payload_class = DecisionMakingPayload
    synchronized_data_class = SynchronizedData

    def end_block(self) -> Optional[Tuple[BaseSynchronizedData, Event]]:
        """Process the end of the block."""

        if self.threshold_reached:
            payload = json.loads(self.most_voted_payload)
            event = Event(payload["event"])
            synchronized_data = cast(SynchronizedData, self.synchronized_data)

            # Ensure property data is always serialized
            # property_id = payload.get("property_data", {}).get("property_id", None)
            # if property_id and not isinstance(property_id, str):
            #     payload["property_data"]["property_id"] = json.dumps(
            #         property_id, sort_keys=True
            #     )

            # property_value = payload.get("property_data", {}).get(
            #     "property_value", None
            # )
            # if property_value and not isinstance(property_value, str):
            #     payload["property_data"]["property_value"] = json.dumps(
            #         property_value, sort_keys=True
            #     )

            synchronized_data = synchronized_data.update(
                synchronized_data_class=SynchronizedData,
                **payload.get("property_data", {})
            )
            return synchronized_data, event

        if not self.is_majority_possible(
            self.collection, self.synchronized_data.nb_participants
        ):
            return self.synchronized_data, Event.NO_MAJORITY

        return None

    # Event.DONE, Event.ERROR, Event.TRANSACT, Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class TxPreparationRound(CollectSameUntilThresholdRound):
    """TxPreparationRound"""

    payload_class = TxPreparationPayload
    synchronized_data_class = SynchronizedData
    done_event = Event.DONE
    no_majority_event = Event.NO_MAJORITY
    collection_key = get_name(SynchronizedData.participant_to_tx_round)
    selection_key = (
        get_name(SynchronizedData.tx_submitter),
        get_name(SynchronizedData.most_voted_tx_hash),
    )

    # Event.ROUND_TIMEOUT  # this needs to be referenced for static checkers


class FinishedDecisionMakingRound(DegenerateRound):
    """FinishedDecisionMakingRound"""


class FinishedTxPreparationRound(DegenerateRound):
    """FinishedLearningRound"""


class LearningAbciApp(AbciApp[Event]):
    """LearningAbciApp"""

    initial_round_cls: AppState = APICheckRound
    initial_states: Set[AppState] = {
        APICheckRound,
    }
    transition_function: AbciAppTransitionFunction = {
        APICheckRound: {
            Event.NO_MAJORITY: APICheckRound,
            Event.ROUND_TIMEOUT: APICheckRound,
            Event.DONE: DecisionMakingRound,
        },
        DecisionMakingRound: {
            Event.NO_MAJORITY: DecisionMakingRound,
            Event.ROUND_TIMEOUT: DecisionMakingRound,
            Event.DONE: FinishedDecisionMakingRound,
            Event.ERROR: FinishedDecisionMakingRound,
            Event.TRANSACT: TxPreparationRound,
        },
        TxPreparationRound: {
            Event.NO_MAJORITY: TxPreparationRound,
            Event.ROUND_TIMEOUT: TxPreparationRound,
            Event.DONE: FinishedTxPreparationRound,
        },
        FinishedDecisionMakingRound: {},
        FinishedTxPreparationRound: {},
    }
    final_states: Set[AppState] = {
        FinishedDecisionMakingRound,
        FinishedTxPreparationRound,
    }
    event_to_timeout: EventToTimeout = {}
    cross_period_persisted_keys: FrozenSet[str] = frozenset()
    db_pre_conditions: Dict[AppState, Set[str]] = {
        APICheckRound: set(),
    }
    db_post_conditions: Dict[AppState, Set[str]] = {
        FinishedDecisionMakingRound: set(),
        FinishedTxPreparationRound: {get_name(SynchronizedData.most_voted_tx_hash)},
    }
