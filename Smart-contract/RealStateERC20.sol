// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

contract RealEstateMarketWithERC20 {
    struct Property {
        uint256 id;
        string name;
        address owner;
        uint256 value;
        bool forSale;
    }

    mapping(uint256 => Property) public properties;
    mapping(address => uint256[]) public ownerProperties;
    uint256 public nextPropertyId;
    address public contractOwner;
    IERC20 public token;

    event PropertyRegistered(uint256 id, string name, address owner, uint256 value);
    event PropertyListedForSale(uint256 id, uint256 value);
    event PropertySold(uint256 id, address oldOwner, address newOwner, uint256 value);

    modifier onlyOwner(uint256 _propertyId) {
        require(properties[_propertyId].owner == msg.sender, "Only the owner can perform this action");
        _;
    }

    modifier propertyExists(uint256 _propertyId) {
        require(properties[_propertyId].owner != address(0), "Property does not exist");
        _;
    }

    modifier isForSale(uint256 _propertyId) {
        require(properties[_propertyId].forSale, "Property is not for sale");
        _;
    }

    modifier isNotForSale(uint256 _propertyId) {
        require(!properties[_propertyId].forSale, "Property is already for sale");
        _;
    }

    constructor(address _tokenAddress) {
        contractOwner = msg.sender;
        token = IERC20(_tokenAddress);
    }

    function registerProperty(string memory _name, uint256 _value) public {
        properties[nextPropertyId] = Property({
            id: nextPropertyId,
            name: _name,
            owner: msg.sender,
            value: _value,
            forSale: false
        });
        ownerProperties[msg.sender].push(nextPropertyId);

        emit PropertyRegistered(nextPropertyId, _name, msg.sender, _value);
        nextPropertyId++;
    }

    function listPropertyForSale(uint256 _propertyId, uint256 _salePrice) public onlyOwner(_propertyId) isNotForSale(_propertyId) {
        properties[_propertyId].value = _salePrice;
        properties[_propertyId].forSale = true;

        emit PropertyListedForSale(_propertyId, _salePrice);
    }

    function buyProperty(uint256 _propertyId) public propertyExists(_propertyId) isForSale(_propertyId) {
        uint256 salePrice = properties[_propertyId].value;
        require(token.transferFrom(msg.sender, properties[_propertyId].owner, salePrice), "Token transfer failed");

        address previousOwner = properties[_propertyId].owner;

        // Transfer ownership
        properties[_propertyId].owner = msg.sender;
        properties[_propertyId].forSale = false;

        // Remove property from previous owner's list
        uint256[] storage ownedProperties = ownerProperties[previousOwner];
        for (uint256 i = 0; i < ownedProperties.length; i++) {
            if (ownedProperties[i] == _propertyId) {
                ownedProperties[i] = ownedProperties[ownedProperties.length - 1];
                ownedProperties.pop();
                break;
            }
        }

        // Add property to new owner's list
        ownerProperties[msg.sender].push(_propertyId);

        emit PropertySold(_propertyId, previousOwner, msg.sender, salePrice);
    }

    function getPropertyDetails(uint256 _propertyId) public view returns (string memory, address, uint256, bool) {
        Property memory property = properties[_propertyId];
        return (property.name, property.owner, property.value, property.forSale);
    }

    function getOwnerProperties(address _owner) public view returns (uint256[] memory) {
        return ownerProperties[_owner];
    }

    function getPropertiesForSale() public view returns (Property[] memory) {
        uint256 count = 0;
        for (uint256 i = 0; i < nextPropertyId; i++) {
            if (properties[i].forSale) {
                count++;
            }
        }

        Property[] memory propertiesForSale = new Property[](count);
        uint256 index = 0;
        for (uint256 i = 0; i < nextPropertyId; i++) {
            if (properties[i].forSale) {
                propertiesForSale[index] = properties[i];
                index++;
            }
        }
        return propertiesForSale;
    }
}