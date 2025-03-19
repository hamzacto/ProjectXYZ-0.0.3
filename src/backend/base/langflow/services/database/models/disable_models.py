"""
This module provides utility functions to dynamically enable or disable
SQLModel models during runtime to prevent database migration issues with
models that have tables that don't exist in the database.
"""

from typing import List, Type
import inspect
import sys
from sqlmodel import SQLModel
from loguru import logger

# List of model modules that should be disabled during migrations
DISABLED_MODEL_MODULES = [
    "langflow.services.database.models.file.model",
    "langflow.services.database.models.email_thread.model",
    "langflow.services.database.models.processed_email.model",
]

# Original module dictionaries to restore later
_original_modules = {}


def disable_migration_models() -> None:
    """
    Temporarily disables SQLModel models that are causing migration issues
    by modifying their __table_args__ to include {'extend_existing': True}
    """
    for module_name in DISABLED_MODEL_MODULES:
        try:
            if module_name in sys.modules:
                logger.debug(f"Disabling models in module: {module_name}")
                
                # Save the original module for later restoration
                _original_modules[module_name] = sys.modules[module_name]
                
                # Get the model classes from the module
                module = sys.modules[module_name]
                model_classes = _get_sqlmodel_classes(module)
                
                # Modify each model class to make it migration-safe
                for model_class in model_classes:
                    if hasattr(model_class, '__table__') and model_class.__table__ is not None:
                        logger.debug(f"Setting 'extend_existing' for model: {model_class.__name__}")
                        # Add extend_existing to table_args
                        if hasattr(model_class, '__table_args__'):
                            if isinstance(model_class.__table_args__, dict):
                                model_class.__table_args__['extend_existing'] = True
                            else:
                                # If it's a tuple, convert to a list, add the dict and convert back
                                args_list = list(model_class.__table_args__)
                                extend_dict = {'extend_existing': True}
                                # Add the dict if not already present
                                if not any(isinstance(arg, dict) for arg in args_list):
                                    args_list.append(extend_dict)
                                model_class.__table_args__ = tuple(args_list)
                        else:
                            model_class.__table_args__ = {'extend_existing': True}
        except Exception as e:
            logger.error(f"Error disabling models in {module_name}: {str(e)}")


def _get_sqlmodel_classes(module) -> List[Type[SQLModel]]:
    """
    Get all SQLModel subclasses from a module
    """
    return [
        obj for _, obj in inspect.getmembers(module) 
        if inspect.isclass(obj) and issubclass(obj, SQLModel) and obj != SQLModel
    ]


def restore_migration_models() -> None:
    """
    Restores the original modules after migrations are complete
    """
    for module_name, original_module in _original_modules.items():
        try:
            logger.debug(f"Restoring original module: {module_name}")
            sys.modules[module_name] = original_module
        except Exception as e:
            logger.error(f"Error restoring module {module_name}: {str(e)}")
    
    # Clear the saved modules
    _original_modules.clear()
