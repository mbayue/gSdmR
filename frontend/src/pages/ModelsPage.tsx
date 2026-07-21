import { useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import { useModels, useDeleteModel } from '../hooks/useModels';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../components/ui/dialog';
import ModelForm from '../components/models/ModelForm';
import type { Model } from '../types';

export default function ModelsPage() {
  const { data: models = [], isLoading } = useModels();
  const deleteModel = useDeleteModel();
  const [editingModel, setEditingModel] = useState<Model | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Model | null>(null);

  const handleDelete = () => {
    if (!deleteTarget) return;
    deleteModel.mutate(deleteTarget.id, {
      onSuccess: () => {
        toast.success(`Model "${deleteTarget.name}" deleted`);
        setDeleteTarget(null);
      },
      onError: () => toast.error('Failed to delete model'),
    });
  };

  const handleEdit = (model: Model) => {
    setEditingModel(model);
    setShowForm(true);
  };

  const handleAdd = () => {
    setEditingModel(null);
    setShowForm(true);
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingModel(null);
  };

  if (isLoading) {
    return <div className="text-muted-foreground text-sm">Loading models...</div>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Models</h1>
          <p className="text-sm text-muted-foreground">Define model aliases and provider routing</p>
        </div>
        <Button onClick={handleAdd} size="sm">
          <Plus className="h-4 w-4" />
          Add Model
        </Button>
      </div>

      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Model Name</TableHead>
              <TableHead>Mode</TableHead>
              <TableHead>Provider Routes</TableHead>
              <TableHead className="w-[100px]">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {models.map((m) => (
              <TableRow key={m.id}>
                <TableCell className="font-mono font-medium">{m.name}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="text-xs">{m.load_balance}</Badge>
                </TableCell>
                <TableCell>
                  <div className="flex flex-wrap gap-1.5">
                    {m.providers.map((p, i) => (
                      <Badge key={i} variant="secondary" className="text-xs font-normal">
                        {p.priority}. {p.provider_name} → {p.provider_model}
                      </Badge>
                    ))}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" onClick={() => handleEdit(m)}>
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => setDeleteTarget(m)}>
                      <Trash2 className="h-4 w-4 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {models.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                  No models configured yet. Add a model to start routing.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      {/* Add/Edit Dialog */}
      <Dialog open={showForm} onOpenChange={(open) => !open && handleFormClose()}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{editingModel ? 'Edit Model' : 'Add Model'}</DialogTitle>
            <DialogDescription>
              {editingModel
                ? 'Update the model routing configuration.'
                : 'Create a model alias and configure provider routing.'}
            </DialogDescription>
          </DialogHeader>
          <ModelForm model={editingModel} onClose={handleFormClose} />
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Model</DialogTitle>
            <DialogDescription>
              Are you sure you want to delete &quot;{deleteTarget?.name}&quot;? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={handleDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
