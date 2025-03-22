import React, { useCallback, useEffect, useState } from 'react';
import { useDropzone } from 'react-dropzone';
import {
  Upload,
  File,
  FolderOpen,
  AlertCircle,
  CheckCircle2,
  Loader2,
  Trash2,
  HelpCircle,
  Plus,
} from 'lucide-react';
import BaseModal from '@/modals/baseModal';
import type { FileItem, FileCategory } from './types';
import { Button } from '@/components/ui/button';
import IconComponent, { ForwardedIconComponent } from '@/components/common/genericIconComponent';
import ShadTooltip from '@/components/common/shadTooltipComponent';
import './style.css';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { IconBook, IconDatabase } from '@tabler/icons-react';
import { Badge } from '@/components/ui/badge';
interface FileUploadProps {
  fileCategories: FileCategory[];
  setFileCategories: React.Dispatch<React.SetStateAction<FileCategory[]>>;
  activeCategory: string;
  setActiveCategory: (categoryId: string) => void;
  onFilesUpdate: (files: FileItem[]) => void;
}

export default function KnowledgeBaseFilesUpload({
  fileCategories,
  setFileCategories,
  activeCategory,
  setActiveCategory,
  onFilesUpdate,
}: FileUploadProps) {
  const [error, setError] = useState<string | null>(null);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [fileToDelete, setFileToDelete] = useState<string | null>(null);
  const [categoryToDelete, setCategoryToDelete] = useState<string | null>(null);
  const [isDeleteCategoryDialogOpen, setIsDeleteCategoryDialogOpen] = useState(false);

  // Update parent component whenever files are updated
  useEffect(() => {
    const activeCategoryFiles =
      fileCategories.find((c) => c.id === activeCategory)?.files || [];
    onFilesUpdate(activeCategoryFiles);
  }, [fileCategories, activeCategory, onFilesUpdate]);

  // Helper function to update a file's properties in state by its id
  const updateFileState = (fileId: string, newProps: Partial<FileItem>) => {
    setFileCategories((prevCategories) =>
      prevCategories.map((category) => ({
        ...category,
        files: category.files?.map((file) =>
          file.id === fileId ? { ...file, ...newProps } : file
        ),
      }))
    );
  };

  const onDrop = useCallback(
    (acceptedFiles: File[], rejectedFiles: any[]) => {
      setError(null);

      if (rejectedFiles.length > 0) {
        setError(
          'Some files were rejected. Supported formats: PDF, TXT, DOC, DOCX. Max size: 50MB.'
        );
      }

      acceptedFiles.forEach((file) => {
        // Generate a unique id for the file
        const fileId = Math.random().toString(36).substr(2, 9);

        // Create a new file item with initial "processing" state
        const newFile: FileItem = {
          id: fileId,
          name: file.name,
          size: file.size,
          type: file.type,
          category: activeCategory,
          status: 'processing',
          progress: 0,
          content: null,
          file_path: '',
        };

        // Add the new file immediately to the active category
        setFileCategories((prevCategories) =>
          prevCategories.map((category) =>
            category.id === activeCategory
              ? { ...category, files: [...(category.files || []), newFile] }
              : category
          )
        );

        const reader = new FileReader();

        // Update progress based on the FileReader's progress event
        reader.onprogress = (event) => {
          if (event.lengthComputable) {
            const percent = Math.round((event.loaded / event.total) * 100);
            updateFileState(fileId, { progress: percent });
          }
        };

        // On successful load, update the file's content and mark it as completed
        reader.onload = () => {
          updateFileState(fileId, {
            content: reader.result,
            status: 'completed',
            progress: 100,
          });
        };

        // Handle errors during file reading
        reader.onerror = () => {
          updateFileState(fileId, {
            status: 'error',
            progress: 0,
            // Optionally, set an error message
            error: reader.error ? reader.error.message : 'Error reading file',
          });
        };

        // Read the file as a Base64 encoded URL
        reader.readAsDataURL(file);
      });
    },
    [activeCategory, setFileCategories]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'text/plain': ['.txt'],
      'application/msword': ['.doc'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': [
        '.docx',
      ],
    },
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  const addCategory = () => {
    setIsDialogOpen(true);
  };

  const handleAddCategory = () => {
    if (newCategoryName.trim()) {
      setFileCategories((prevCategories: FileCategory[]) => [
        ...prevCategories,
        {
          id: Math.random().toString(36).substr(2, 9),
          name: newCategoryName.trim(),
          files: [],
        },
      ]);
      setNewCategoryName('');
      setIsDialogOpen(false);
    }
  };

  const deleteFile = (fileId: string) => {
    setFileToDelete(fileId);
    setIsDeleteDialogOpen(true);
  };

  const handleDeleteFile = () => {
    if (fileToDelete) {
      setFileCategories((prevCategories: FileCategory[]) =>
        prevCategories.map((category) => ({
          ...category,
          files: category.files.filter((file) => file.id !== fileToDelete),
        }))
      );
      setFileToDelete(null);
      setIsDeleteDialogOpen(false);
    }
  };

  const deleteCategory = (categoryId: string) => {
    const category = fileCategories.find(c => c.id === categoryId);
    // Don't allow deletion of the General category
    if (category && category.name === 'General') {
      setError('The General category cannot be deleted.');
      return;
    }
    setCategoryToDelete(categoryId);
    setIsDeleteCategoryDialogOpen(true);
  };

  const handleDeleteCategory = () => {
    if (categoryToDelete) {
      // Get the category to delete
      const categoryToRemove = fileCategories.find(c => c.id === categoryToDelete);

      // Find the General category (or first category if no General)
      const generalCategory = fileCategories.find(c => c.name === 'General') || fileCategories[0];

      if (categoryToRemove && generalCategory) {
        // Move files from the deleted category to the General category
        const filesToMove = categoryToRemove.files || [];

        setFileCategories((prevCategories: FileCategory[]) => {
          // First update the General category with the moved files
          const updatedCategories = prevCategories.map(category =>
            category.id === generalCategory.id
              ? {
                ...category,
                files: [...category.files, ...filesToMove.map(file => ({ ...file, category: generalCategory.id }))]
              }
              : category
          );

          // Then filter out the category to delete
          return updatedCategories.filter(category => category.id !== categoryToDelete);
        });

        // If the active category is being deleted, switch to the General category
        if (activeCategory === categoryToDelete) {
          setActiveCategory(generalCategory.id);
        }
      }

      setCategoryToDelete(null);
      setIsDeleteCategoryDialogOpen(false);
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return (
          <IconComponent
            name="CheckCircle2"
            className="w-5 h-5 text-green-500"
          />
        );
      case 'error':
        return (
          <IconComponent
            name="AlertCircle"
            className="w-5 h-5 text-red-500"
          />
        );
      case 'processing':
        return (
          <IconComponent
            name="Loader2"
            className="w-5 h-5 text-blue-500 animate-spin"
          />
        );
      default:
        return (
          <IconComponent
            name="File"
            className="w-5 h-5 text-gray-500"
          />
        );
    }
  };

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-8 h-[calc(100vh-200px)]">
      <BaseModal.Header description="Upload your documents and files to train your AI agent. Supported formats: PDF, TXT, DOC, DOCX">
        <span className="flex items-center gap-2">
          <IconDatabase className="w-5 h-5" />
          Knowledge Base
        </span>
      </BaseModal.Header>

      {error && (
        <div className="bg-red-50 p-4 rounded-lg text-red-600 mb-6">
          <IconComponent
            name="AlertCircle"
            className="inline-block w-5 h-5 mr-2"
          />
          {error}
        </div>
      )}

      <div className="flex gap-6 flex-1 min-h-0 dark:bg-[#18181b]">
        <div className="w-1/4 flex flex-col">
          <div className="bg-white dark:bg-[#18181b] rounded-lg shadow-sm border border-gray-100 dark:border-gray-800">
            <div className="p-4 border-b border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-gray-700 dark:text-gray-200">Categories</h3>
                </div>
                <Button
                  onClick={addCategory}
                  variant="ghost"
                  size="sm"
                  className="text-primary hover:text-primary/90 flex items-center gap-1"
                >
                  <IconComponent name="Plus" className="w-3.5 h-3.5" />
                  Add
                </Button>
              </div>
            </div>
            <div className="p-2 max-h-[200px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600">
              {fileCategories.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-6 text-center text-gray-500 dark:text-gray-400">
                  <p className="text-sm">No categories yet</p>
                  <p className="text-xs mt-1">Click "Add" to create your first category</p>
                </div>
              ) : (
                fileCategories.map((category) => (
                  <Button
                    key={category.id}
                    onClick={() => setActiveCategory(category.id)}
                    variant="ghost"
                    className={`w-full justify-between text-left px-3 py-2 mb-1 rounded-md transition-all duration-200 group ${activeCategory === category.id
                      ? 'bg-primary/10 text-primary dark:bg-primary/20 font-medium'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                      }`}
                  >
                    <div className="flex items-center gap-2">
                      <span className="truncate">{category.name}</span>
                    </div>
                    <div className="flex items-center">
                      {category.name !== 'General' ? (
                        <div className="relative">
                          <Badge className="ml-2 text-xs px-2 py-0.5 rounded-full transition-opacity duration-200 min-w-[26px] inline-flex items-center justify-center group-hover:opacity-0" variant="secondaryStatic">{category.files.length}</Badge>
                          <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200 ml-2 dark:bg-transparent">
                            <Button
                              size="icon"
                              onClick={(e) => {
                                e.stopPropagation();
                                deleteCategory(category.id);
                              }}
                              className="h-7 w-7 text-muted-foreground hover:text-destructive bg-background:transparent dark:bg-transparent"
                              variant="ghost"
                              aria-label="Delete category"
                              >
                              <ForwardedIconComponent name="Trash2" className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <Badge className="ml-2 text-xs px-2 py-0.5 rounded-full min-w-[26px] inline-flex items-center justify-center" variant="secondaryStatic">
                          {category.files.length}
                        </Badge>
                      )}
                    </div>
                  </Button>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="flex-1 flex flex-col h-full">
          <div
            {...getRootProps()}
            className={`
              relative border-2 border-dashed rounded-lg p-6 shrink-0 mb-4
              transition-all duration-200 ease-in-out cursor-pointer
              ${isDragActive
                ? 'border-primary bg-primary/5 dark:border-primary/70 dark:bg-primary/10'
                : 'border-gray-300 hover:border-primary/50 dark:border-gray-700'
              }
            `}
          >
            <input {...getInputProps()} />
            <div className="flex flex-col items-center gap-3">
              <div className="p-3 bg-primary/10 rounded-full">
                <IconComponent
                  name="Upload"
                  className="w-8 h-8 text-primary"
                />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {isDragActive ? 'Drop files here...' : 'Drag and drop files, or click to browse'}
                </p>
                <p className="mt-1 text-xs text-gray-500">
                  Supported formats: PDF, TXT, DOC, DOCX (Max 50MB)
                </p>
              </div>
            </div>
          </div>

          <div className="flex-1 bg-white dark:bg-[#18181b] rounded-lg shadow-sm border border-gray-100 dark:border-gray-800 overflow-hidden">
            <div className="p-4 border-b border-gray-100 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <IconComponent name="File" className="w-4 h-4 text-primary" />
                  <h3 className="font-medium text-gray-700 dark:text-gray-200">
                    {fileCategories.find(c => c.id === activeCategory)?.name || ''} Files
                  </h3>
                </div>
                <span className="text-xs text-gray-500">
                  {fileCategories.find(c => c.id === activeCategory)?.files.length || 0} file(s)
                </span>
              </div>
            </div>
            <div className="h-[250px] overflow-y-auto scrollbar-thin scrollbar-thumb-gray-300 dark:scrollbar-thumb-gray-600">
              {!fileCategories.find((c) => c.id === activeCategory) ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-4 text-gray-500">
                  <IconComponent name="FolderOpen" className="w-8 h-8 mb-2 text-gray-400" />
                  <p className="text-sm font-medium">No category selected</p>
                  <p className="text-xs mt-1">Select a category to view files</p>
                </div>
              ) : fileCategories.find((c) => c.id === activeCategory)?.files.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-4 text-gray-500">
                  <IconComponent name="File" className="w-8 h-8 mb-2 text-gray-400" />
                  <p className="text-sm font-medium">No files in this category</p>
                  <p className="text-xs mt-1">Drag and drop files above to add them</p>
                </div>
              ) : (
                <div className="divide-y dark:divide-gray-700">
                  {fileCategories.find((c) => c.id === activeCategory)?.files.map((file) => (
                    <div
                      key={file.id}
                      className="p-4 flex items-center gap-4 group hover:bg-gray-50 dark:hover:bg-gray-800/60 transition-colors"
                    >
                      <div className="flex-shrink-0 p-2 rounded-full bg-gray-100 dark:bg-gray-800">
                        {getStatusIcon(file.status)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between">
                          <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                            {file.name}
                          </p>
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                            <ShadTooltip content="Remove file" side="top" align="center">
                              <Button
                                onClick={() => deleteFile(file.id)}
                                variant="ghost"
                                size="iconMd"
                                className="h-7 w-7 text-muted-foreground hover:text-destructive bg-background:transparent"
                              >
                                <IconComponent name="Trash2" className="h-4 w-4" />
                              </Button>
                            </ShadTooltip>
                          </div>
                        </div>
                        {file.status === 'processing' && (
                          <div className="mt-2">
                            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-1.5">
                              <div
                                className="bg-primary h-1.5 rounded-full transition-all duration-300"
                                style={{ width: `${file.progress}%` }}
                              />
                            </div>
                            <p className="text-xs text-gray-500 mt-1">Processing: {file.progress}%</p>
                          </div>
                        )}
                        {file.status === 'completed' && (
                          <p className="text-xs text-gray-500 mt-1">
                            {(file.size / 1024).toFixed(1)} KB
                          </p>
                        )}
                        {file.status === 'error' && (
                          <p className="text-xs text-red-500 mt-1">
                            {file.error || 'Error processing file'}
                          </p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add New Category</DialogTitle>
            <DialogDescription>
              Enter a name for your new document category
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="name">Category name</Label>
              <Input
                id="name"
                value={newCategoryName}
                onChange={(e) => setNewCategoryName(e.target.value)}
                placeholder="Enter category name"
                className="col-span-3"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleAddCategory}>Add Category</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isDeleteDialogOpen} onOpenChange={setIsDeleteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              <div className="flex items-center">
                <span className="pr-2">Delete File</span>
                <IconComponent
                  name="Trash2"
                  className="h-6 w-6 pl-1 text-foreground"
                />
              </div>
            </DialogTitle>
          </DialogHeader>
          <div className="py-3">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Are you sure you want to delete this file?
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              This action cannot be undone.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsDeleteDialogOpen(false);
                setFileToDelete(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteFile}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={isDeleteCategoryDialogOpen} onOpenChange={setIsDeleteCategoryDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              <div className="flex items-center">
                <span className="pr-2">Delete Category</span>
                <IconComponent
                  name="Trash2"
                  className="h-6 w-6 pl-1 text-foreground"
                />
              </div>
            </DialogTitle>
          </DialogHeader>
          <div className="py-3">
            <p className="text-sm text-gray-600 dark:text-gray-300">
              Are you sure you want to delete this category?
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              All files in this category will be moved to the General category.
            </p>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              This action cannot be undone.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setIsDeleteCategoryDialogOpen(false);
                setCategoryToDelete(null);
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteCategory}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}