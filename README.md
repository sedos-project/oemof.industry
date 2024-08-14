
# Oemof Industry

Holds the `MultiInputMultiOutputConverter` for modeling industrial components.

## Introduction

The `MultiInputMultiOutputConverter` (MIMOConverter), `MIMO` facade and `CO2EmissionLimit` were developed for the SEDOS project.
The MIMOConverter is designed to handle multiple inputs and multiple outputs, enabling advanced modeling of
industrial components with the oemof framework.
The `MIMO` facade simplifies the use of the MIMOConverter with `oemof.tabular`.
Additionally, `CO2EmissionLimit` is provided to add an CO2 limit to an energy system based on CO2, CH4 and N2O flows.

This documentation provides a comprehensive guide to understanding, using, and integrating the MIMO features in your projects.

## Installation
To install *oemof.industry* follow these steps:

* Clone *oemof.industry*  `git clone https://github.com/sedos-project/oemof.industry.git`
* enter folder `cd oemof.industry`
* create virtual environment using conda: `conda env create -f environment.yml`
* activate environment: `conda activate oemof.industry`
* install oemof.instry package using poetry, via: `poetry install`

## Development
Install `oemof.industry` via:

    pip install -e .

To run the all tests run:

    pytest

## Usage
To use oemof.industry features in a project:

    from oemof.industry import MultiInputMultiOutputConverter, MIMO, CO2EmissionLimit

### MIMOConverter


### MIMO facade


### CO2EmissionLimit

## API Reference

## Contributing
