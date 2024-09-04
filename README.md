
# Oemof Industry

Holds the `MultiInputMultiOutputConverter` for modeling industrial components.

## Introduction

The features in this repo were developed for the SEDOS project:

* `MultiInputMultiOutputConverter` (MIMOConverter)
* `MIMO` facade
* `CO2EmissionLimit`

The MIMOConverter is designed to handle multiple inputs and multiple outputs, enabling advanced modeling of
industrial components with the oemof framework.
The `MIMO` facade simplifies the use of the MIMOConverter with [`oemof.tabular`](https://github.com/oemof/oemof-tabular), which loads oemof energy systems from tabular data sources.
Additionally, `CO2EmissionLimit` is provided to add an emission constraint to an energy system based on CO2, CH4 and N2O flows.

## Installation
To install *oemof.industry* follow these steps:

* Clone *oemof.industry*  `git clone https://github.com/sedos-project/oemof.industry.git`
* enter folder `cd oemof.industry`
* create virtual environment using conda: `conda env create -f environment.yml`
* activate environment: `conda activate oemof.industry`
* install oemof.instry package using poetry, via: `poetry install`

## Development

To run the all tests run:

    pytest

## Usage
To use oemof.industry features in a project:

    from oemof_industry.mimo_converter import MultiInputMultiOutputConverter, MIMO
    from oemof_industry. emission_constraint import CO2EmissionLimit

### MIMOConverter


### MIMO facade


### CO2EmissionLimit

## API Reference

## Contributing
