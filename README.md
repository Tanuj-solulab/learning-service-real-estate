# Real Estate Market Service

This service interacts with the RealEstateMarketWithERC20 contract to manage real estate properties, enabling the registration, listing, and sale of properties using ERC-20 tokens.

## Deployment Details
- Smart Contract Address: [Add your deployed contract address here]
- ERC-20 Token Address: [Add your deployed token address here]

## Overview
The RealEstateMarketWithERC20 contract allows users to register properties, list them for sale, and buy properties using ERC-20 tokens. The service integrates with this contract to facilitate seamless property transactions.

## Current Logic
### Property Registration
Users can register new properties with a name and value. Each property is assigned a unique ID and is initially not for sale.

### Listing for Sale
Property owners can list their properties for sale by setting the `forSale` flag to true. Only the owner of a property can list it for sale.

### Buying Property
Users can buy listed properties using ERC-20 tokens. The service checks for the required token allowance and transfers the tokens from the buyer to the seller. Upon successful transfer, the property ownership is updated, and the property is removed from the previous owner's list and added to the new owner's list.

## Current Workflow
### Property Registration
1. Call `registerProperty(string _name, uint256 _value)` to register a new property.
2. The property is assigned a unique ID and stored in the `properties` mapping.
3. The property is added to the `ownerProperties` mapping for the current owner.

### Listing for Sale
1. The property owner calls a function to list the property for sale.
2. The `forSale` flag of the property is set to true.
3. The property is now available for purchase.

### Buying Property
1. The buyer checks the properties available for sale.
2. The buyer approves the required token amount to the contract.
3. The buyer calls `buyProperty(uint256 _propertyId)` to purchase the property.
4. The contract checks the token allowance and transfers the tokens from the buyer to the seller.
5. The property ownership is transferred to the buyer, and the property is removed from the previous owner's list and added to the buyer's list.

## Future Enhancements
- Implementing more advanced property management features, such as property valuation updates and rental agreements.
- Enhancing the service to handle multiple property listings and transactions concurrently.
- Integrating external data sources for property valuation and market analysis.

This service ensures efficient management of real estate properties by leveraging the OLAS framework for dynamic and secure property transactions using ERC-20 tokens.
