import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Form, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage } from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import ForwardedIconComponent from "@/components/common/genericIconComponent";
import { useForm } from "react-hook-form";
import * as z from "zod";
import { zodResolver } from "@hookform/resolvers/zod";

type VariableType = "Text" | "Long Text" | "Number" | "JSON";

interface Variable {
  id: string;
  name: string;
  type: VariableType;
  defaultValue: string;
  required: boolean;
}

interface ConfigureTemplateStepProps {
  variables?: Variable[];
  onVariablesChange?: (variables: Variable[]) => void;
}

// Form validation schema
const formSchema = z.object({
  name: z.string()
    .min(1, "Variable name is required")
    .regex(/^[a-zA-Z0-9_]+$/, "Variable name can only contain letters, numbers, and underscores"),
  type: z.enum(["Text", "Long Text", "Number", "JSON"]),
  defaultValue: z.string().optional(),
  required: z.boolean().default(false)
});

// Badge variant mapping for each variable type
const typeVariantMap: Record<VariableType, React.ComponentProps<typeof Badge>["variant"]> = {
  "Text": "default",
  "Long Text": "secondary",
  "Number": "destructive",
  "JSON": "outline"
};

export default function GuidedAiAgentConfigureTemplate({ variables: externalVariables, onVariablesChange }: ConfigureTemplateStepProps) {
  const [variables, setVariables] = useState<Variable[]>(externalVariables || []);
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [editingVariable, setEditingVariable] = useState<Variable | null>(null);
  
  // Sync with external variables when they change
  useEffect(() => {
    if (externalVariables) {
      setVariables(externalVariables);
    }
  }, [externalVariables]);

  // Form setup with react-hook-form
  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      type: "Text",
      defaultValue: "",
      required: false
    },
  });

  // Update parent component when variables change
  const updateVariables = (newVariables: Variable[]) => {
    setVariables(newVariables);
    if (onVariablesChange) {
      onVariablesChange(newVariables);
    }
  };

  // Handle adding or editing a variable
  const onSubmit = (values: z.infer<typeof formSchema>) => {
    if (editingVariable) {
      // Edit existing variable
      const updatedVariables = variables.map(variable => 
        variable.id === editingVariable.id 
          ? { ...variable, ...values } 
          : variable
      );
      updateVariables(updatedVariables);
    } else {
      // Add new variable
      const newVariable: Variable = {
        id: crypto.randomUUID(),
        ...values,
        defaultValue: values.defaultValue || "",
        required: values.required
      };
      updateVariables([...variables, newVariable]);
    }
    
    closeDialog();
  };

  // Open dialog for adding a new variable
  const openAddDialog = () => {
    form.reset({
      name: "",
      type: "Text",
      defaultValue: "",
      required: false
    });
    setEditingVariable(null);
    setIsAddDialogOpen(true);
  };

  // Open dialog for editing a variable
  const openEditDialog = (variable: Variable) => {
    form.reset({
      name: variable.name,
      type: variable.type,
      defaultValue: variable.defaultValue,
      required: variable.required
    });
    setEditingVariable(variable);
    setIsAddDialogOpen(true);
  };

  // Close dialog and reset form
  const closeDialog = () => {
    setIsAddDialogOpen(false);
    setTimeout(() => {
      form.reset();
      setEditingVariable(null);
    }, 100);
  };

  // Delete a variable
  const deleteVariable = (id: string) => {
    const newVariables = variables.filter(variable => variable.id !== id);
    updateVariables(newVariables);
  };

  // Check if a variable name already exists (for validation)
  const isNameDuplicate = (name: string): boolean => {
    if (!editingVariable) {
      return variables.some(v => v.name === name);
    }
    return variables.some(v => v.name === name && v.id !== editingVariable.id);
  };

  return (
    <div className="w-full flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold">Configure Template Variables</h1>
        <p className="text-sm text-muted-foreground">
          Define variables that can be used in your agent template. These variables can be referenced in your prompts using double braces (e.g., {'{{variable_name}}'}).
        </p>
      </div>

      {/* Variables table */}
      <div className="border rounded-md">
        {variables.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Variable</TableHead>
                <TableHead>Default Value</TableHead>
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {variables.map((variable) => (
                <TableRow key={variable.id}>
                  <TableCell className="font-medium">
                    <div className="flex items-center">
                      <span className="mr-1">{variable.name}</span>
                      <Badge variant={typeVariantMap[variable.type]} size="sm">
                        {variable.type}
                      </Badge>
                      {variable.required && (
                        <Badge variant="gray" className="ml-1" size="sm">Required</Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="truncate max-w-[300px]">
                    {variable.defaultValue || <span className="text-muted-foreground italic">None</span>}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        onClick={() => openEditDialog(variable)}
                        className="h-8 w-8"
                      >
                        <ForwardedIconComponent name="Pencil" className="h-4 w-4" />
                      </Button>
                      <Button 
                        variant="ghost" 
                        size="icon" 
                        onClick={() => deleteVariable(variable.id)}
                        className="h-8 w-8 text-destructive hover:text-destructive"
                      >
                        <ForwardedIconComponent name="Trash2" className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="flex flex-col items-center justify-center py-8 text-center">
            <ForwardedIconComponent name="Variable" className="h-10 w-10 text-muted-foreground mb-2" />
            <h3 className="font-medium">No variables defined</h3>
            <p className="text-sm text-muted-foreground mt-1 mb-4">
              Add a variable to customize your agent template
            </p>
            <Button 
              variant="outline"
              onClick={openAddDialog}
              className="mt-2"
            >
              <ForwardedIconComponent name="Plus" className="mr-2 h-4 w-4" />
              Add your first variable
            </Button>
          </div>
        )}
      </div>

      {variables.length > 0 && (
        <Button 
          variant="outline"
          onClick={openAddDialog}
          className="w-full"
        >
          <ForwardedIconComponent name="Plus" className="mr-2 h-4 w-4" />
          Add Variable
        </Button>
      )}

      {/* Add/Edit Variable Dialog */}
      <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editingVariable ? "Edit Variable" : "Add Variable"}
            </DialogTitle>
            <DialogDescription>
              {editingVariable 
                ? "Modify the variable's properties" 
                : "Create a new variable to use in your template"}
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Variable Name <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input 
                        placeholder="company_name" 
                        {...field} 
                        onChange={(e) => {
                          const value = e.target.value;
                          field.onChange(value);
                          
                          // Check for duplicates
                          if (isNameDuplicate(value)) {
                            form.setError("name", {
                              type: "manual",
                              message: "This variable name already exists"
                            });
                          } else {
                            form.clearErrors("name");
                          }
                        }}
                      />
                    </FormControl>
                    <FormDescription>
                      Use this in your prompts as {'{{' + field.value + '}}'}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Type <span className="text-destructive">*</span>
                    </FormLabel>
                    <Select 
                      onValueChange={field.onChange} 
                      defaultValue={field.value}
                      value={field.value}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a type" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="Text">Text</SelectItem>
                        <SelectItem value="Long Text">Long Text</SelectItem>
                        <SelectItem value="Number">Number</SelectItem>
                        <SelectItem value="JSON">JSON</SelectItem>
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      The type determines how users will input the variable value
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="defaultValue"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Default Value</FormLabel>
                    <FormControl>
                      {form.watch("type") === "Long Text" || form.watch("type") === "JSON" ? (
                        <Textarea 
                          placeholder={form.watch("type") === "JSON" ? '{ "key": "value" }' : "Enter default value..."}
                          className="min-h-24"
                          {...field} 
                        />
                      ) : form.watch("type") === "Number" ? (
                        <Input 
                          type="number"
                          placeholder="0"
                          {...field}
                          onChange={(e) => field.onChange(e.target.value)}
                        />
                      ) : (
                        <Input 
                          placeholder="Enter default value..." 
                          {...field} 
                        />
                      )}
                    </FormControl>
                    <FormDescription>
                      Optional default value for this variable (users can override this)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="required"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-start space-x-3 space-y-0 rounded-md border p-4">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel>
                        Required
                      </FormLabel>
                      <FormDescription>
                        Users must provide a value for this variable
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button type="button" variant="outline" onClick={closeDialog}>
                  Cancel
                </Button>
                <Button type="submit">
                  {editingVariable ? "Save Changes" : "Add Variable"}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
