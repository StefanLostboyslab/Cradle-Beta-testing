# Cradle.py - Digital Product Passport Dashboard
# Adapted from FusionWhatt.py logic

import adsk.core, adsk.fusion, adsk.cam, traceback, json

# --- CONFIGURATION ---
APP_VERSION = '0.64'  # Must match Dashboard version
DASHBOARD_URL = 'https://cradle-products-375243024916.us-central1.run.app'
PALETTE_ID = 'cradle_dashboard_palette_v10'
PALETTE_TITLE = 'Cradle Dashboard v{}'.format(APP_VERSION)
CMD_SHOW_ID = 'cmdShowCradle_v2'
CMD_WRITE_META_ID = 'cmdWriteMeta_v1'
CMD_READ_META_ID = 'cmdReadMeta_v1'
CMD_SYNC_FILENAME_ID = 'cmdSyncFilename_v1'
ATTR_GROUP = 'CRADLE'  # Attribute group name for DPP metadata

# URL Commands
CMD_ABOUT_ID = 'cmdAboutWhatt_v1'
CMD_HELP_ID = 'cmdHelpSupport_v1'
URL_ABOUT = 'https://whatt.io/'
URL_HELP = 'https://discover.whatt.io/'
URL_LOGIN = 'https://whatt.io/login'
# ---------------------

_app = None
_ui = None
_handlers = []

class ShowPaletteCommandExecuteHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            command = args.command
            onExecute = ShowPaletteCommandExecute()
            command.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class ShowPaletteCommandExecute(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            palette = _ui.palettes.itemById(PALETTE_ID)
            if not palette:
                # Fixed Size: 400 x 850
                palette = _ui.palettes.add(PALETTE_ID, PALETTE_TITLE, DASHBOARD_URL, True, True, False, 400, 850)
                palette.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
                
                # ENFORCE SIZE (Prevent Docking Auto-Scale)
                palette.setMinimumSize(400, 850)
                palette.setMaximumSize(400, 850)
                
                # Register HTML event handler for receiving data from JS
                onHTMLEvent = PaletteHTMLEventHandler()
                palette.incomingFromHTML.add(onHTMLEvent)
                _handlers.append(onHTMLEvent)
            else:
                palette.title = PALETTE_TITLE
                palette.isVisible = True
                # Re-apply constraints on show to be safe
                palette.setMinimumSize(400, 850)
                palette.setMaximumSize(400, 850)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class PaletteHTMLEventHandler(adsk.core.HTMLEventHandler):
    """Handles incoming data from the React dashboard via adsk.fusionSendData."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            htmlArgs = adsk.core.HTMLEventArgs.cast(args)
            action = htmlArgs.action
            data = htmlArgs.data
            
            if action == 'syncMetadata':
                # Parse JSON and write to design attributes
                metadata = json.loads(data)
                
                design = adsk.fusion.Design.cast(_app.activeProduct)
                if not design:
                    _ui.messageBox('No active design to sync metadata to.')
                    return
                
                rootComp = design.rootComponent
                count = 0
                
                for key, value in metadata.items():
                    if value:  # Skip empty values
                        # Remove existing attribute if present
                        existingAttr = rootComp.attributes.itemByName(ATTR_GROUP, key)
                        if existingAttr:
                            existingAttr.deleteMe()
                        
                        # Add new attribute
                        rootComp.attributes.add(ATTR_GROUP, key, str(value))
                        count += 1
                
                _ui.messageBox('✓ Synced {} metadata fields to Fusion design!'.format(count))
                
                # After sync, send updated metadata back to dashboard
                self.sendDesignMetadataToDashboard()
            
            elif action == 'getDesignMetadata':
                # Dashboard is requesting current design metadata
                self.sendDesignMetadataToDashboard()
            
            elif action == 'syncFilename':
                # Dashboard is requesting to sync the filename
                design = adsk.fusion.Design.cast(_app.activeProduct)
                if not design:
                    _ui.messageBox('No active design.')
                    return
                
                rootComp = design.rootComponent
                prdIdAttr = rootComp.attributes.itemByName(ATTR_GROUP, 'PRD_ID')
                nameAttr = rootComp.attributes.itemByName(ATTR_GROUP, 'product_name')
                
                if not prdIdAttr:
                    _ui.messageBox('No PRD_ID found in metadata. Sync metadata first.')
                    return
                
                prd_id = prdIdAttr.value
                product_name = nameAttr.value if nameAttr else 'Untitled'
                new_doc_name = '{} {}'.format(prd_id, product_name)
                
                import re
                safe_doc_name = re.sub(r'[\\/:*?"<>|]', '_', new_doc_name)
                
                doc = _app.activeDocument
                if doc and doc.dataFile:
                    try:
                        if doc.dataFile.name != safe_doc_name:
                            doc.dataFile.name = safe_doc_name
                            _ui.messageBox('✓ Document renamed to:\n{}'.format(safe_doc_name))
                        else:
                            _ui.messageBox('Document is already named:\n{}'.format(safe_doc_name))
                        # Refresh metadata to show updated filename
                        self.sendDesignMetadataToDashboard()
                    except Exception as e:
                        _ui.messageBox('Error renaming document:\n{}'.format(str(e)))
                elif doc and not doc.isSaved:
                    try:
                        if doc.name != safe_doc_name:
                            doc.name = safe_doc_name
                            _ui.messageBox('✓ Document renamed to:\n{}\n\n(Save to persist)'.format(safe_doc_name))
                        else:
                            _ui.messageBox('Document is already named:\n{}'.format(safe_doc_name))
                        self.sendDesignMetadataToDashboard()
                    except Exception as e:
                        _ui.messageBox('Error renaming document:\n{}'.format(str(e)))
                else:
                    _ui.messageBox('Cannot rename document.')
            
            elif action == 'openUrl':
                # Dashboard is requesting to open a URL in the browser
                import webbrowser
                if data:
                    webbrowser.open(data)
            
            elif action == 'searchDesigns':
                # Dashboard is requesting to search for matching design files
                # WIDENED: Search ALL projects with fuzzy keyword matching
                search_data = json.loads(data)
                product_name = search_data.get('productName', '').lower()
                product_number = search_data.get('productNumber', '').lower()
                
                # Extract meaningful keywords (skip common/short words)
                skip_words = {'the', 'and', 'for', 'with', 'from', 'driver', 'inch', 'high', 'low', 'pro'}
                search_terms = []
                
                if product_name:
                    # Split into words and keep meaningful ones (4+ chars)
                    for word in product_name.split():
                        # Remove special chars
                        clean_word = ''.join(c for c in word if c.isalnum())
                        if len(clean_word) >= 3 and clean_word not in skip_words:
                            search_terms.append(clean_word)
                
                if product_number:
                    # Add product number as exact term
                    search_terms.append(product_number.replace('-', '').replace('_', ''))
                
                if not search_terms:
                    _ui.messageBox('No search terms found.\n\nTry a product with a more descriptive name.')
                    return
                
                # Search ACTIVE PROJECT ONLY (fast) with fuzzy matching
                matches = []
                project_name = 'Active Project'
                try:
                    doc = _app.activeDocument
                    if doc and doc.dataFile:
                        # Get the project containing the active document
                        active_folder = doc.dataFile.parentFolder
                        while active_folder.parentFolder:
                            active_folder = active_folder.parentFolder
                        project_name = active_folder.name if hasattr(active_folder, 'name') else 'Active Project'
                        
                        # Search this project recursively (depth-limited to 2 for speed)
                        self.searchFolderRecursive(active_folder, search_terms, matches, project_name, max_results=15, max_depth=2, current_depth=0)
                    
                    # Also search currently open documents
                    for i in range(_app.documents.count):
                        if len(matches) >= 15:
                            break
                        open_doc = _app.documents.item(i)
                        if open_doc and open_doc.name:
                            fname_lower = open_doc.name.lower()
                            for term in search_terms:
                                if term in fname_lower:
                                    # Avoid duplicates
                                    if not any(m[0] == open_doc.name for m in matches):
                                        matches.append((open_doc.name, '(Open)', open_doc))
                                    break
                                    
                except Exception as e:
                    _ui.messageBox('Search error: {}'.format(str(e)))
                    return
                
                if not matches:
                    _ui.messageBox('No matching designs found in "{}".\n\nSearched for: {}\n\nTip: Open a design from the project you want to search.'.format(
                        project_name, ', '.join(search_terms[:5])))
                    return
                
                # Show results
                result_text = 'Found {} match(es) in "{}":\n\n'.format(len(matches), project_name)
                for i, item in enumerate(matches[:15]):
                    if len(item) >= 2:
                        fname, project = item[0], item[1]
                        # Truncate long names
                        display_name = fname[:35] + '...' if len(fname) > 38 else fname
                        result_text += '{}. {} [{}]\n'.format(i+1, display_name, project[:15])
                result_text += '\nEnter number to open (or Cancel):'
                
                (choice, cancelled) = _ui.inputBox(result_text, 'Search Results', '1')
                
                if cancelled:
                    return
                
                try:
                    idx = int(choice.strip()) - 1
                    if 0 <= idx < len(matches):
                        item = matches[idx]
                        fname, project, obj = item[0], item[1], item[2]
                        if hasattr(obj, 'activate'):
                            # It's an open document
                            obj.activate()
                        else:
                            # It's a DataFile
                            _app.documents.open(obj)
                        _ui.messageBox('Opened: {}'.format(fname))
                except Exception as e:
                    _ui.messageBox('Could not open: {}'.format(str(e)))
                
        except:
            if _ui:
                _ui.messageBox('Event Handler Failed:\n{}'.format(traceback.format_exc()))
    
    def searchFolderFlat(self, folder, search_terms, matches, project_name, max_results=10):
        """Fast non-recursive search - only files in the given folder."""
        if len(matches) >= max_results:
            return
        
        try:
            # Search files in this folder only (not subfolders)
            for i in range(folder.dataFiles.count):
                if len(matches) >= max_results:
                    break
                datafile = folder.dataFiles.item(i)
                fname_lower = datafile.name.lower()
                
                # Check if any search term matches
                for term in search_terms:
                    if term in fname_lower:
                        matches.append((datafile.name, project_name, datafile))
                        break
        except:
            pass  # Ignore errors
    
    def searchFolderRecursive(self, folder, search_terms, matches, project_name, max_results=20, max_depth=3, current_depth=0):
        """Recursively search a DataFolder with depth limit for performance."""
        if len(matches) >= max_results or current_depth > max_depth:
            return
        
        try:
            # Search files in this folder
            for i in range(folder.dataFiles.count):
                if len(matches) >= max_results:
                    break
                datafile = folder.dataFiles.item(i)
                fname_lower = datafile.name.lower()
                
                # Check if ANY search term matches (fuzzy - just needs one match)
                for term in search_terms:
                    if term in fname_lower:
                        # Avoid duplicates
                        if not any(m[0] == datafile.name for m in matches):
                            matches.append((datafile.name, project_name, datafile))
                        break
            
            # Recurse into subfolders (with depth limit)
            if current_depth < max_depth:
                for i in range(folder.dataFolders.count):
                    if len(matches) >= max_results:
                        break
                    subfolder = folder.dataFolders.item(i)
                    self.searchFolderRecursive(subfolder, search_terms, matches, project_name, max_results, max_depth, current_depth + 1)
        except:
            pass  # Ignore errors accessing folders
    
    def searchFolder(self, folder, search_terms, matches, project_name, max_results=20):
        """Recursively search a DataFolder for matching files."""
        if len(matches) >= max_results:
            return
        
        try:
            # Search files in this folder
            for i in range(folder.dataFiles.count):
                if len(matches) >= max_results:
                    break
                datafile = folder.dataFiles.item(i)
                fname_lower = datafile.name.lower()
                
                # Check if any search term matches
                for term in search_terms:
                    if term in fname_lower:
                        matches.append((datafile.name, project_name, datafile))
                        break
            
            # Recurse into subfolders
            for i in range(folder.dataFolders.count):
                if len(matches) >= max_results:
                    break
                self.searchFolder(folder.dataFolders.item(i), search_terms, matches, project_name, max_results)
        except:
            pass  # Ignore errors accessing folders
    
    def sendDesignMetadataToDashboard(self):
        """Reads CRADLE attributes from current design and sends to dashboard."""
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            palette = _ui.palettes.itemById(PALETTE_ID)
            
            if not palette:
                return
            
            if not design:
                # No design open
                palette.sendInfoToHTML('designMetadata', json.dumps({
                    'designName': None,
                    'metadata': None
                }))
                return
            
            rootComp = design.rootComponent
            attrs = rootComp.attributes
            
            # Collect all CRADLE attributes
            cradle_attrs = {}
            for i in range(attrs.count):
                attr = attrs.item(i)
                if attr.groupName == ATTR_GROUP:
                    cradle_attrs[attr.name] = attr.value
            
            # Get design/document name
            doc = _app.activeDocument
            designName = doc.name if doc else 'Unnamed Design'
            
            # Send to dashboard
            payload = {
                'designName': designName,
                'metadata': cradle_attrs if cradle_attrs else None
            }
            palette.sendInfoToHTML('designMetadata', json.dumps(payload))
            
        except:
            if _ui:
                _ui.messageBox('Send Metadata Failed:\n{}'.format(traceback.format_exc()))

# --- METADATA COMMANDS ---

class WriteMetadataHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = WriteMetadataExecute()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class WriteMetadataExecute(adsk.core.CommandEventHandler):
    """Writes DPP metadata to the active design's root component as Attributes."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            if not design:
                _ui.messageBox('No active design.')
                return
            
            rootComp = design.rootComponent
            
            # Prompt for JSON input (simplified - in production, get from dashboard)
            (json_input, cancelled) = _ui.inputBox(
                'Paste DPP metadata as JSON:\n{"PRD_ID": "PRD-26-00106", "GTIN": "123...", ...}',
                'Write Metadata',
                ''
            )
            
            if cancelled or not json_input:
                return
            
            try:
                data = json.loads(json_input.strip())
            except json.JSONDecodeError as e:
                _ui.messageBox('Invalid JSON: {}'.format(str(e)))
                return
            
            # Write each key-value pair as an attribute
            count = 0
            for key, value in data.items():
                # Remove existing attribute if present
                existingAttr = rootComp.attributes.itemByName(ATTR_GROUP, key)
                if existingAttr:
                    existingAttr.deleteMe()
                
                # Add new attribute
                rootComp.attributes.add(ATTR_GROUP, key, str(value))
                count += 1
            
            _ui.messageBox('✓ Wrote {} attributes to root component.'.format(count))
            
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class ReadMetadataHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = ReadMetadataExecute()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class ReadMetadataExecute(adsk.core.CommandEventHandler):
    """Reads all CRADLE attributes from the root component and displays them."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            if not design:
                _ui.messageBox('No active design.')
                return
            
            rootComp = design.rootComponent
            attrs = rootComp.attributes
            
            # Collect all CRADLE attributes
            cradle_attrs = {}
            for i in range(attrs.count):
                attr = attrs.item(i)
                if attr.groupName == ATTR_GROUP:
                    cradle_attrs[attr.name] = attr.value
            
            if not cradle_attrs:
                _ui.messageBox('No CRADLE metadata found in this design.')
                return
            
            # Format for display
            lines = ['=== CRADLE DPP Metadata ===', '']
            for key, value in cradle_attrs.items():
                lines.append('{}: {}'.format(key, value))
            
            _ui.messageBox('\n'.join(lines))
            
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class SyncFilenameHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = SyncFilenameExecute()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class SyncFilenameExecute(adsk.core.CommandEventHandler):
    """Renames the active document to match PRD_ID + product_name from metadata."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            if not design:
                _ui.messageBox('No active design.')
                return
            
            rootComp = design.rootComponent
            
            # Get PRD_ID from attributes
            prdIdAttr = rootComp.attributes.itemByName(ATTR_GROUP, 'PRD_ID')
            nameAttr = rootComp.attributes.itemByName(ATTR_GROUP, 'product_name')
            
            if not prdIdAttr:
                _ui.messageBox('No PRD_ID found in metadata. Write metadata first.')
                return
            
            prd_id = prdIdAttr.value
            product_name = nameAttr.value if nameAttr else 'Untitled'
            
            new_doc_name = '{} {}'.format(prd_id, product_name)
            
            import re
            safe_doc_name = re.sub(r'[\\/:*?"<>|]', '_', new_doc_name)
            
            # Rename the active document
            doc = _app.activeDocument
            if not doc:
                _ui.messageBox('No active document to rename.')
                return
            
            # For saved documents (cloud), use dataFile.name
            # For unsaved documents, use doc.name
            if doc.dataFile:
                try:
                    # Document is saved - use dataFile to rename
                    if doc.dataFile.name != safe_doc_name:
                        doc.dataFile.name = safe_doc_name
                        _ui.messageBox('✓ Document renamed to:\n{}'.format(safe_doc_name))
                    else:
                        _ui.messageBox('Document is already named:\n{}'.format(safe_doc_name))
                except Exception as e:
                    _ui.messageBox('Error renaming document:\n{}'.format(str(e)))
            elif not doc.isSaved:
                try:
                    # Document is not saved yet - can use doc.name
                    if doc.name != safe_doc_name:
                        doc.name = safe_doc_name
                        _ui.messageBox('✓ Document renamed to:\n{}\n\n(Save the document to persist the name)'.format(safe_doc_name))
                    else:
                        _ui.messageBox('Document is already named:\n{}'.format(safe_doc_name))
                except Exception as e:
                    _ui.messageBox('Error renaming document:\n{}'.format(str(e)))
            else:
                _ui.messageBox('Cannot rename: Document state not supported.')
            
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# --- CLEAR METADATA COMMAND ---
CMD_CLEAR_META_ID = 'cmdClearMeta_v1'

class ClearMetadataHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = ClearMetadataExecute()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class ClearMetadataExecute(adsk.core.CommandEventHandler):
    """Clears all CRADLE metadata from the active design."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            if not design:
                _ui.messageBox('No active design.')
                return
            
            rootComp = design.rootComponent
            attrs = rootComp.attributes
            
            # Collect all CRADLE attributes
            to_delete = []
            for i in range(attrs.count):
                attr = attrs.item(i)
                if attr.groupName == ATTR_GROUP:
                    to_delete.append(attr)
            
            if not to_delete:
                _ui.messageBox('No CRADLE metadata found in this design.')
                return
            
            # Confirm deletion
            (result, cancelled) = _ui.inputBox(
                'This will delete {} CRADLE metadata attributes.\nType "DELETE" to confirm:'.format(len(to_delete)),
                'Clear Metadata',
                ''
            )
            
            if cancelled or result.strip().upper() != 'DELETE':
                _ui.messageBox('Operation cancelled.')
                return
            
            # Delete all CRADLE attributes
            count = 0
            for attr in to_delete:
                attr.deleteMe()
                count += 1
            
            _ui.messageBox('✓ Cleared {} CRADLE metadata attributes from design.'.format(count))
            
            # Notify dashboard of the change
            palette = _ui.palettes.itemById(PALETTE_ID)
            if palette:
                import json
                palette.sendInfoToHTML('designMetadata', json.dumps({
                    'designName': _app.activeDocument.name if _app.activeDocument else 'Unnamed',
                    'metadata': None
                }))
                
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# --- CREATE DPP SKETCH COMMAND ---
CMD_CREATE_SKETCH_ID = 'cmdCreateDPPSketch_v1'

class CreateDPPSketchHandler(adsk.core.CommandCreatedEventHandler):
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = CreateDPPSketchExecute()
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

class CreateDPPSketchExecute(adsk.core.CommandEventHandler):
    """Creates a sketch with DPP metadata text in the design."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        try:
            design = adsk.fusion.Design.cast(_app.activeProduct)
            if not design:
                _ui.messageBox('No active design.')
                return
            
            rootComp = design.rootComponent
            attrs = rootComp.attributes
            
            # Collect all CRADLE attributes
            metadata = {}
            for i in range(attrs.count):
                attr = attrs.item(i)
                if attr.groupName == ATTR_GROUP:
                    metadata[attr.name] = attr.value
            
            if not metadata:
                _ui.messageBox('No CRADLE metadata found. Sync metadata first.')
                return
            
            # Build formatted text
            lines = ['=== DPP METADATA ===']
            for key, value in sorted(metadata.items()):
                if value and value.strip() and value != '---':
                    lines.append('{}: {}'.format(key, value))
            lines.append('=' * 20)
            
            text_content = '\n'.join(lines)
            
            # Create a sketch on XZ plane (bottom/floor plane - text lies flat)
            sketches = rootComp.sketches
            xzPlane = rootComp.xZConstructionPlane
            
            # Check if sketch already exists
            for i in range(sketches.count):
                sk = sketches.item(i)
                if sk.name == 'DPP Metadata':
                    sk.deleteMe()
                    break
            
            sketch = sketches.add(xzPlane)
            sketch.name = 'DPP Metadata'
            
            # Add text to sketch (height in cm)
            textHeight = 0.5  # 5mm
            sketchTexts = sketch.sketchTexts
            
            # Create text input
            textInput = sketchTexts.createInput2(text_content, textHeight)
            
            # Set as multi-line text at origin
            origin = adsk.core.Point3D.create(0, 0, 0)
            cornerPoint = adsk.core.Point3D.create(10, -5, 0)  # Width, height
            textInput.setAsMultiLine(origin, cornerPoint, adsk.core.HorizontalAlignments.LeftHorizontalAlignment, adsk.core.VerticalAlignments.TopVerticalAlignment, 0)
            
            # Add the text
            sketchTexts.add(textInput)
            
            _ui.messageBox('✓ Created "DPP Metadata" sketch with {} fields'.format(len(metadata)))
            
        except:
            if _ui:
                _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

# --- DOCUMENT EVENT HANDLERS ---
# These handlers detect when the active document changes and refresh the dashboard

def sendMetadataUpdateToDashboard():
    """Helper function to send current design metadata to dashboard."""
    try:
        design = adsk.fusion.Design.cast(_app.activeProduct)
        palette = _ui.palettes.itemById(PALETTE_ID)
        
        if not palette or not palette.isVisible:
            return
        
        if not design:
            palette.sendInfoToHTML('designMetadata', json.dumps({
                'designName': None,
                'metadata': None
            }))
            return
        
        rootComp = design.rootComponent
        attrs = rootComp.attributes
        
        # Collect CRADLE attributes
        cradle_attrs = {}
        for i in range(attrs.count):
            attr = attrs.item(i)
            if attr.groupName == ATTR_GROUP:
                cradle_attrs[attr.name] = attr.value
        
        # Get design name
        doc = _app.activeDocument
        designName = doc.name if doc else 'Unnamed Design'
        
        # Send to dashboard
        payload = {
            'designName': designName,
            'metadata': cradle_attrs if cradle_attrs else None
        }
        palette.sendInfoToHTML('designMetadata', json.dumps(payload))
    except:
        pass  # Silently ignore errors during event handling

class DocumentActivatedHandler(adsk.core.DocumentEventHandler):
    """Fires when a document becomes the active document."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        sendMetadataUpdateToDashboard()

class DocumentCreatedHandler(adsk.core.DocumentEventHandler):
    """Fires when a new document is created."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        # Small delay to let the document fully initialize
        import time
        adsk.doEvents()
        sendMetadataUpdateToDashboard()

class DocumentOpenedHandler(adsk.core.DocumentEventHandler):
    """Fires when a document is opened."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        adsk.doEvents()
        sendMetadataUpdateToDashboard()

class DocumentSavedHandler(adsk.core.DocumentEventHandler):
    """Fires when a document is saved (filename may change)."""
    def __init__(self):
        super().__init__()
    def notify(self, args):
        sendMetadataUpdateToDashboard()

# --- URL COMMAND HANDLERS ---

class OpenUrlHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for URL-opening commands (About, Help, etc.)"""
    def __init__(self, url):
        super().__init__()
        self.url = url
    def notify(self, args):
        try:
            cmd = args.command
            onExecute = OpenUrlExecute(self.url)
            cmd.execute.add(onExecute)
            _handlers.append(onExecute)
        except:
            if _ui:
                _ui.messageBox('Command Failed:\n{}'.format(traceback.format_exc()))

class OpenUrlExecute(adsk.core.CommandEventHandler):
    """Executes opening a URL in the browser."""
    def __init__(self, url):
        super().__init__()
        self.url = url
    def notify(self, args):
        try:
            import webbrowser
            webbrowser.open(self.url)
        except:
            if _ui:
                _ui.messageBox('Failed to open URL:\n{}'.format(traceback.format_exc()))

# --- RUN / STOP ---

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface
        
        # 1. Create Layout in Solid Environment (Design Tab)
        workspaces = _ui.workspaces
        modelingWorkspace = workspaces.itemById('FusionSolidEnvironment')
        toolbarPanels = modelingWorkspace.toolbarPanels
        
        # =====================================
        # SINGLE PANEL with TWO promoted icons
        # =====================================
        cradlePanel = toolbarPanels.itemById('CradlePanel')
        if cradlePanel: cradlePanel.deleteMe()
        
        # Remove old whattio panel if exists
        whattioPanel = toolbarPanels.itemById('WhattioPanel')
        if whattioPanel: whattioPanel.deleteMe()
        
        cradlePanel = toolbarPanels.add('CradlePanel', 'Cradle DPP v{}'.format(APP_VERSION), 'SelectPanel', False)

        # --- FIRST ICON: whatt.io (promoted to show in panel header) ---
        cmdWhattio = _ui.commandDefinitions.itemById(CMD_ABOUT_ID)
        if cmdWhattio: cmdWhattio.deleteMe()
        cmdWhattio = _ui.commandDefinitions.addButtonDefinition(CMD_ABOUT_ID, 'whatt.io', 'Open whatt.io website', './resources/whattio')
        
        onWhattioCreated = OpenUrlHandler(URL_ABOUT)
        cmdWhattio.commandCreated.add(onWhattioCreated)
        _handlers.append(onWhattioCreated)
        
        whattioControl = cradlePanel.controls.addCommand(cmdWhattio)
        whattioControl.isPromoted = True  # Shows as icon in panel header
        whattioControl.isPromotedByDefault = True

        # --- SECOND ICON: Open Dashboard (promoted to show in panel header) ---

        cmdDef = _ui.commandDefinitions.itemById(CMD_SHOW_ID)
        if cmdDef: cmdDef.deleteMe()
        cmdDef = _ui.commandDefinitions.addButtonDefinition(CMD_SHOW_ID, 'Open Dashboard', 'Open the Cradle Dashboard', './resources/cmdShowCradle')
        
        onCommandCreated = ShowPaletteCommandExecuteHandler()
        cmdDef.commandCreated.add(onCommandCreated)
        _handlers.append(onCommandCreated)
        
        dashboardControl = cradlePanel.controls.addCommand(cmdDef)
        dashboardControl.isPromoted = True  # Shows as icon in panel header
        dashboardControl.isPromotedByDefault = True

        # --- Separator before dropdown menu items ---
        cradlePanel.controls.addSeparator()

        # Help & Support (dropdown item)
        cmdHelp = _ui.commandDefinitions.itemById(CMD_HELP_ID)
        if cmdHelp: cmdHelp.deleteMe()
        cmdHelp = _ui.commandDefinitions.addButtonDefinition(CMD_HELP_ID, 'Help & Support', 'Documentation and support for Cradle DPP')
        
        onHelpCreated = OpenUrlHandler(URL_HELP)
        cmdHelp.commandCreated.add(onHelpCreated)
        _handlers.append(onHelpCreated)
        
        cradlePanel.controls.addCommand(cmdHelp)

        # Login to whatt.io (dropdown item)
        CMD_LOGIN_ID = 'cmdWhattioLogin_v1'
        cmdLogin = _ui.commandDefinitions.itemById(CMD_LOGIN_ID)
        if cmdLogin: cmdLogin.deleteMe()
        cmdLogin = _ui.commandDefinitions.addButtonDefinition(CMD_LOGIN_ID, 'Login to whatt.io', 'Open whatt.io login page')
        
        onLoginCreated = OpenUrlHandler(URL_LOGIN)
        cmdLogin.commandCreated.add(onLoginCreated)
        _handlers.append(onLoginCreated)
        
        cradlePanel.controls.addCommand(cmdLogin)

        # --- Separator before metadata tools ---
        cradlePanel.controls.addSeparator()
        # 3. Command: Write Metadata
        cmdWriteMeta = _ui.commandDefinitions.itemById(CMD_WRITE_META_ID)
        if cmdWriteMeta: cmdWriteMeta.deleteMe()
        cmdWriteMeta = _ui.commandDefinitions.addButtonDefinition(CMD_WRITE_META_ID, 'Write Metadata', 'Store DPP metadata in design')
        
        onWriteMetaCreated = WriteMetadataHandler()
        cmdWriteMeta.commandCreated.add(onWriteMetaCreated)
        _handlers.append(onWriteMetaCreated)
        
        cradlePanel.controls.addCommand(cmdWriteMeta)

        # 5. Command: Read Metadata
        cmdReadMeta = _ui.commandDefinitions.itemById(CMD_READ_META_ID)
        if cmdReadMeta: cmdReadMeta.deleteMe()
        cmdReadMeta = _ui.commandDefinitions.addButtonDefinition(CMD_READ_META_ID, 'Read Metadata', 'Display stored DPP metadata')
        
        onReadMetaCreated = ReadMetadataHandler()
        cmdReadMeta.commandCreated.add(onReadMetaCreated)
        _handlers.append(onReadMetaCreated)
        
        cradlePanel.controls.addCommand(cmdReadMeta)

        # 6. Command: Sync Filename
        cmdSyncFilename = _ui.commandDefinitions.itemById(CMD_SYNC_FILENAME_ID)
        if cmdSyncFilename: cmdSyncFilename.deleteMe()
        cmdSyncFilename = _ui.commandDefinitions.addButtonDefinition(CMD_SYNC_FILENAME_ID, 'Sync Filename', 'Rename document to PRD-ID + Name')
        
        onSyncFilenameCreated = SyncFilenameHandler()
        cmdSyncFilename.commandCreated.add(onSyncFilenameCreated)
        _handlers.append(onSyncFilenameCreated)
        
        cradlePanel.controls.addCommand(cmdSyncFilename)

        # 7. Command: Clear Metadata (Beta)
        cmdClearMeta = _ui.commandDefinitions.itemById(CMD_CLEAR_META_ID)
        if cmdClearMeta: cmdClearMeta.deleteMe()
        cmdClearMeta = _ui.commandDefinitions.addButtonDefinition(CMD_CLEAR_META_ID, 'Clear Metadata', 'Remove all CRADLE metadata from design (Beta)')
        
        onClearMetaCreated = ClearMetadataHandler()
        cmdClearMeta.commandCreated.add(onClearMetaCreated)
        _handlers.append(onClearMetaCreated)
        
        cradlePanel.controls.addCommand(cmdClearMeta)

        # 8. Command: Create DPP Sketch
        cmdCreateSketch = _ui.commandDefinitions.itemById(CMD_CREATE_SKETCH_ID)
        if cmdCreateSketch: cmdCreateSketch.deleteMe()
        cmdCreateSketch = _ui.commandDefinitions.addButtonDefinition(CMD_CREATE_SKETCH_ID, 'Create DPP Sketch', 'Create a sketch with DPP metadata text')
        
        onCreateSketchCreated = CreateDPPSketchHandler()
        cmdCreateSketch.commandCreated.add(onCreateSketchCreated)
        _handlers.append(onCreateSketchCreated)
        
        cradlePanel.controls.addCommand(cmdCreateSketch)

        # 9. Register Document Event Handlers (auto-refresh dashboard on design change)
        onDocActivated = DocumentActivatedHandler()
        _app.documentActivated.add(onDocActivated)
        _handlers.append(onDocActivated)
        
        onDocCreated = DocumentCreatedHandler()
        _app.documentCreated.add(onDocCreated)
        _handlers.append(onDocCreated)
        
        onDocOpened = DocumentOpenedHandler()
        _app.documentOpening.add(onDocOpened)
        _handlers.append(onDocOpened)
        
        onDocSaved = DocumentSavedHandler()
        _app.documentSaved.add(onDocSaved)
        _handlers.append(onDocSaved)

    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

def stop(context):
    try:
        if _ui:
            # Clean up palette
            palette = _ui.palettes.itemById(PALETTE_ID)
            if palette: palette.deleteMe()
            
            # Clean up UI - all commands
            for cmd_id in [CMD_SHOW_ID, CMD_WRITE_META_ID, CMD_READ_META_ID, CMD_SYNC_FILENAME_ID, CMD_CLEAR_META_ID, CMD_CREATE_SKETCH_ID, CMD_ABOUT_ID, CMD_HELP_ID]:
                cmd = _ui.commandDefinitions.itemById(cmd_id)
                if cmd: cmd.deleteMe()
            
            # Clean up panels
            panel = _ui.workspaces.itemById('FusionSolidEnvironment').toolbarPanels.itemById('CradlePanel')
            if panel: panel.deleteMe()
            
            whattioPanel = _ui.workspaces.itemById('FusionSolidEnvironment').toolbarPanels.itemById('WhattioPanel')
            if whattioPanel: whattioPanel.deleteMe()

    except:
        if _ui:
            _ui.messageBox('Failed:\n{}'.format(traceback.format_exc()))

