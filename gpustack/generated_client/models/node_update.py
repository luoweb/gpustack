from typing import TYPE_CHECKING, Any, Dict, List, Type, TypeVar, Union, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.node_update_labels import NodeUpdateLabels


T = TypeVar("T", bound="NodeUpdate")


@_attrs_define
class NodeUpdate:
    """
    Attributes:
        name (str):
        hostname (str):
        address (str):
        labels (Union[Unset, NodeUpdateLabels]):
        state (Union[None, Unset, str]):
    """

    name: str
    hostname: str
    address: str
    labels: Union[Unset, "NodeUpdateLabels"] = UNSET
    state: Union[None, Unset, str] = UNSET
    additional_properties: Dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        name = self.name

        hostname = self.hostname

        address = self.address

        labels: Union[Unset, Dict[str, Any]] = UNSET
        if not isinstance(self.labels, Unset):
            labels = self.labels.to_dict()

        state: Union[None, Unset, str]
        if isinstance(self.state, Unset):
            state = UNSET
        else:
            state = self.state

        field_dict: Dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "hostname": hostname,
                "address": address,
            }
        )
        if labels is not UNSET:
            field_dict["labels"] = labels
        if state is not UNSET:
            field_dict["state"] = state

        return field_dict

    @classmethod
    def from_dict(cls: Type[T], src_dict: Dict[str, Any]) -> T:
        from ..models.node_update_labels import NodeUpdateLabels

        d = src_dict.copy()
        name = d.pop("name")

        hostname = d.pop("hostname")

        address = d.pop("address")

        _labels = d.pop("labels", UNSET)
        labels: Union[Unset, NodeUpdateLabels]
        if isinstance(_labels, Unset):
            labels = UNSET
        else:
            labels = NodeUpdateLabels.from_dict(_labels)

        def _parse_state(data: object) -> Union[None, Unset, str]:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            return cast(Union[None, Unset, str], data)

        state = _parse_state(d.pop("state", UNSET))

        node_update = cls(
            name=name,
            hostname=hostname,
            address=address,
            labels=labels,
            state=state,
        )

        node_update.additional_properties = d
        return node_update

    @property
    def additional_keys(self) -> List[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties