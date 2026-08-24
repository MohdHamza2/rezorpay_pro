import { useForm, useFieldArray } from 'react-hook-form';
import { useNavigate } from 'react-router-dom';
import { createSPO } from '../api/spo';
import toast from 'react-hot-toast';
import styles from './Suppliers.module.css'; // Reusing styles

export const SPOBuilder = () => {
  const navigate = useNavigate();
  const { register, control, handleSubmit } = useForm({
    defaultValues: {
      supplier_id: '',
      procurement_method: 'DIRECT',
      warehouse_id: '',
      currency: 'AED',
      items: [{
        product_id: '',
        description: '',
        uom_id: '',
        quantity_ordered: 1,
        unit_price: 0,
        line_number: 1
      }]
    }
  });

  const { fields, append, remove } = useFieldArray({
    control,
    name: 'items'
  });

  const onSubmit = async (data: any) => {
    try {
      await createSPO(data);
      toast.success('SPO Created successfully!');
      navigate('/spo');
    } catch (err: any) {
      toast.error('Failed to create SPO');
    }
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2>Create SPO</h2>
      </div>

      <div className={styles.tableContainer} style={{ padding: '2rem' }}>
        <form onSubmit={handleSubmit(onSubmit)} style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label>Supplier ID (UUID)</label><br/>
            <input {...register('supplier_id', { required: true })} style={{ width: '300px', padding: '0.5rem' }} />
          </div>

          <div>
            <label>Warehouse ID (UUID)</label><br/>
            <input {...register('warehouse_id', { required: true })} style={{ width: '300px', padding: '0.5rem' }} />
          </div>

          <div>
            <label>Procurement Method</label><br/>
            <select {...register('procurement_method')} style={{ width: '300px', padding: '0.5rem' }}>
              <option value="DIRECT">Direct</option>
              <option value="RFQ">RFQ</option>
              <option value="CONTRACT">Contract</option>
              <option value="EMERGENCY">Emergency</option>
            </select>
          </div>

          <div>
            <label>Currency</label><br/>
            <input {...register('currency')} style={{ width: '300px', padding: '0.5rem' }} />
          </div>

          <h3>Items</h3>
          {fields.map((field, index) => (
            <div key={field.id} style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1rem' }}>
              <input type="hidden" {...register(`items.${index}.line_number` as const)} value={index + 1} />
              <div>
                <label>Product ID</label><br/>
                <input {...register(`items.${index}.product_id` as const, { required: true })} placeholder="UUID" />
              </div>
              <div>
                <label>Description</label><br/>
                <input {...register(`items.${index}.description` as const, { required: true })} />
              </div>
              <div>
                <label>UOM ID</label><br/>
                <input {...register(`items.${index}.uom_id` as const, { required: true })} placeholder="UUID" />
              </div>
              <div>
                <label>Qty</label><br/>
                <input type="number" {...register(`items.${index}.quantity_ordered` as const, { valueAsNumber: true, min: 1 })} />
              </div>
              <div>
                <label>Price</label><br/>
                <input type="number" step="0.01" {...register(`items.${index}.unit_price` as const, { valueAsNumber: true, min: 0 })} />
              </div>
              <button type="button" onClick={() => remove(index)} style={{ marginTop: '1.2rem', padding: '0.2rem 0.5rem' }}>
                Remove
              </button>
            </div>
          ))}

          <button type="button" onClick={() => append({ product_id: '', description: '', uom_id: '', quantity_ordered: 1, unit_price: 0, line_number: fields.length + 1 })} style={{ width: '150px', padding: '0.5rem' }}>
            Add Item
          </button>

          <hr style={{ margin: '1rem 0' }} />

          <div style={{ display: 'flex', gap: '1rem' }}>
            <button type="submit" className={styles.primaryBtn}>Save Draft</button>
            <button type="button" onClick={() => navigate('/spo')} style={{ padding: '0.5rem 1rem' }}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
};
